#!/usr/bin/env python3

from json import loads
from os import chdir, environ
from pathlib import Path

import click
from click import echo
from instaloader import Instaloader, Profile, ProfileNotExistsException, Post, StoryItem

archive_dir: Path = None
data_dir: Path = None
username_file: Path = None
tracking_list_file: Path = None


def echo_warning(text: str) -> None:
    echo(click.style(text, fg="yellow"))


def get_my_username() -> str:
    return username_file.read_text()


def get_tracked_usernames(starting_line: int = 1) -> list[str]:
    usernames: list[str] = []

    echo("Fetching tracking list.")
    with tracking_list_file.open("r") as f:
        lines = f.readlines()

        for i, line in enumerate(lines):
            if i + 1 < starting_line:
                continue

            line = line.strip()
            if not line or line[0] == "#":
                continue

            usernames.append(line.split()[0])

    return usernames


def change_tracked_username(username: str, new_username: str) -> None:
    echo_warning(f"Username change: {username} -> {new_username}")

    echo("Updating tracking list.")
    with tracking_list_file.open("r+") as f:
        lines = f.readlines()

        for i, line in enumerate(lines):
            line = line.strip()
            if not line or line[0] == "#":
                continue

            splitline = line.split()
            if splitline[0] == username:
                splitline[0] = new_username
                lines[i] = " ".join(splitline)
                f.truncate()
                f.writelines(lines)
                return

    raise Exception(f"Username not found: {username}")


@click.group()
@click.option(
    "-d",
    "--archive-dir",
    type=click.Path(
        exists=False, file_okay=False, dir_okay=True, writable=True, path_type=Path
    ),
    default=Path(environ["HOME"], "instarchive"),
    help="Path to the archive directory.",
)
def instarchive(**kwargs):
    global archive_dir
    global data_dir
    global username_file
    global tracking_list_file

    archive_dir = kwargs["archive_dir"]
    data_dir = Path(archive_dir, "data")
    username_file = Path(archive_dir, "username")
    tracking_list_file = Path(archive_dir, "tracking.txt")


@instarchive.command(
    "init",
    short_help="Set up a new archive, or change your username for an archive.",
)
@click.argument("username", type=str, default="")
def init(username: str):
    archive_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)

    if not username:
        echo_warning("No username provided; Instarchive will be run anonymously.")

    username_file.write_text(username)

    if not tracking_list_file.exists():
        tracking_list_file.touch()
        echo("Remember to fill in the tracking list.")

    echo(f"Initialization done. Archive directory: {archive_dir}")


@instarchive.command("login", short_help="Create or renew the session file.")
def login():
    my_username = get_my_username()
    if not my_username:
        echo_warning("No login is required for anonymous use.")
        return

    session = Instaloader()
    session.interactive_login(my_username)
    session.save_session_to_file()
    session.close()


# Function wrapper for the commands that load and utilize an Instaloader session
# for data collection.
def _collection_command(func):
    def collection_command(*args, **kwargs):
        chdir(data_dir)

        session = Instaloader(
            download_comments=True,
            compress_json=False,
            sanitize_paths=True,
            dirname_pattern="{target}",
            filename_pattern="{date_utc}_{typename}",
            title_pattern="{date_utc}_{typename}",
        )

        my_username = get_my_username()
        if my_username:
            try:
                session.load_session_from_file(my_username)
            except:
                echo_warning("Failed to load session; aborting.")
                session.close()
                return

        func(session, *args, **kwargs)

        session.close()

    return collection_command


@instarchive.command(
    "feed",
    short_help="Collect data associated with tracked profiles from your feed.",
)
@click.option(
    "-p",
    "--num-posts",
    type=click.IntRange(1, 1000),
    default=200,
    help="Number of feed posts to iterate.",
)
@_collection_command
def feed(session: Instaloader, **kwargs):
    wanted_target_usernames = get_tracked_usernames()
    known_target_userid_to_names: dict[int, str] = {}
    # The purpose of known_target_userid_to_names is to deal with changes in
    # target usernames, by making use of existing userid files. This will of
    # course not work if collecting data for the target first-time, thus the
    # need for wanted_target_usernames.

    for dir in data_dir.iterdir():
        if not dir.is_dir():
            continue

        userid_file = Path(dir, "userid")
        if not userid_file.is_file():
            continue

        try:
            known_target_userid_to_names[int(userid_file.read_text())] = dir.name
        except:
            echo_warning(f"Invalid userid file: {userid_file}")

    def item_filter(item: Post | StoryItem) -> bool:
        if item.owner_username in wanted_target_usernames:
            return True

        old_owner_username = known_target_userid_to_names.get(item.owner_id)
        if old_owner_username and old_owner_username in wanted_target_usernames:
            change_tracked_username(old_owner_username, item.owner_username)
            return True
        # If old_owner_username is found but also missing from
        # wanted_target_usernames, that means the username was once on the
        # tracking list but got removed, while leaving the corresponding data
        # subdirectory behind. Ignore it and move on.

        return False

    echo("Collecting stories...")
    try:
        session.download_stories(fast_update=True, storyitem_filter=item_filter)
    except:
        echo_warning("Error occurred in downloading stories.")

    echo("Collecting feed posts...")
    try:
        session.download_feed_posts(
            max_count=kwargs["num_posts"], fast_update=True, post_filter=item_filter
        )
    except:
        echo_warning("Error occurred in downloading feed posts.")

    # Instaloader places downloaded items for :feed and :stories into combined
    # directories rather than directories per individual profile, so we need
    # this metadata-parsing kludge to sort out the items by owner and have them
    # end up in the appropriate directories.
    def migrate_items(source_dirname: str) -> None:
        is_successful = True

        source_dir = Path(data_dir, source_dirname)
        if not source_dir.is_dir():
            echo_warning(f"Directory missing: {source_dir}")
            return False

        for metadata_file in source_dir.iterdir():
            if metadata_file.suffix != ".json" or metadata_file.stem.endswith(
                "_comments"
            ):
                continue

            try:
                metadata = loads(metadata_file.read_text())
                target_username = metadata["node"]["owner"]["username"]
            except:
                echo_warning(f"Invalid metadata file: {metadata_file}")
                is_successful = False
                continue

            target_dir = Path(data_dir, target_username)
            if not target_dir.exists():
                target_dir.mkdir()
                Path(target_dir, "userid").write_text(metadata["node"]["owner"]["id"])

            # Move the actual media/comment files associated with metadata_file.
            for file in source_dir.glob(f"{metadata_file.stem}*"):
                file.rename(Path(target_dir, file.name))

        if is_successful:
            try:
                source_dir.rmdir()
            except:
                echo_warning(f"Failed to remove directory: {source_dir}")

    echo("Moving downloaded items...")
    migrate_items("\N{FULLWIDTH COLON}feed")
    migrate_items("\N{FULLWIDTH COLON}stories")


@instarchive.command(
    "everything",
    short_help="Collect all accessible data associated with tracked profiles.",
)
@click.option(
    "-l",
    "--line",
    type=click.IntRange(1),
    default=1,
    help="Start reading the tracking list file from this line.",
)
@_collection_command
def everything(session: Instaloader, **kwargs):
    is_successful = None

    for wanted_target_username in get_tracked_usernames(kwargs["line"]):
        target_dir = Path(data_dir, wanted_target_username)
        target_userid_file = Path(target_dir, "userid")

        echo(f"Processing profile: {wanted_target_username}")

        try:
            target_profile = Profile.from_username(
                session.context, wanted_target_username
            )
        except ProfileNotExistsException:
            if target_userid_file.exists():
                try:
                    target_profile = Profile.from_id(
                        session.context, target_userid_file.read_text()
                    )
                except:
                    echo_warning("\tProfile is deleted (formerly existed).")
                    echo_warning("\tUpdate the tracking list if desired.")
                    continue

                # Getting the profile by its known userid instead of by the
                # username works; the username had therefore been changed.
                echo("\tProfile has new username.")
                change_tracked_username(wanted_target_username, target_profile.username)
                target_dir = target_dir.rename(target_profile.username)
                target_userid_file = Path(target_dir, "userid")
            else:
                # Profile not found after trying both username and userid.
                echo_warning("\tProfile is nonexistent.")
                is_successful = False
                continue
        except:
            echo_warning("\tFailed to fetch profile.")
            is_successful = False
            continue

        if target_profile.is_private and not target_profile.followed_by_viewer:
            echo_warning("\tProfile is private and non-followed.")
            is_successful = False
            continue

        if not target_userid_file.exists():
            echo("\tFirst time downloading this profile.")
            target_dir.mkdir(exist_ok=True)
            target_userid_file.write_text(str(target_profile.userid))

        try:
            session.download_profiles(
                {target_profile},
                profile_pic=True,
                posts=True,
                highlights=True,
                stories=True,
                fast_update=True,
            )
        except:
            echo_warning("Error occurred in downloading profile.")
            is_successful = False
        else:
            if is_successful is None:
                is_successful = True

    if not is_successful:
        if is_successful is None:
            echo_warning("No targets were processed.")
        else:
            echo_warning("One or more error(s) occurred during collection.")


if __name__ == "__main__":
    instarchive()
