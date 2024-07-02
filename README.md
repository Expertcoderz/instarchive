# Instarchive

Instarchive is a command-line utility for collecting and organizing data from
specific Instagram profiles using the [Instaloader](https://github.com/instaloader/instaloader)
Python module.

## Installation

Instarchive is available on [PyPI](https://pypi.org/project/instarchive/).

```sh
pip3 install instarchive
```

## Features

- Downloads items only from a given list of users to track (instead of
  enumerating all followees or downloading the whole feed).

- Sorts items from `:stories` and `:feeds` into directories based on username.

- Responds to username changes and updates the tracking list file automatically.

## Usage

Demo assuming a Unix environment:

```sh
# Set up the archive. Do re-run this command if you've changed your username.
# The username can also be omitted for using Instarchive anonymously (private
# profiles won't be accessible in those cases).
instarchive init 'my_username'

# The file containing a list of users to track. Only data and metadata
# associated with these users will ever be downloaded.
cat << EOF > ~/instarchive/tracking.txt
target_username

# this is a comment
another_target_username
EOF

# Login to Instagram; your password and authentication code, if necessary, will
# be prompted for. Also, re-run this command if your session has expired, as is
# typically the case when HTTP 401 errors prevent content download.
instarchive login

# Download all accessible data (profile info, profile pic, posts, highlights,
# stories etc.) from all of the users named in the tracking list. Optional;
# intended to be run only once or occasionally since it takes a lot of web
# requests to Instagram. Consider the 'feed' command instead for regular runs.
instarchive everything

# Download data (stories and posts) from the users named in the tracking list,
# only based on what is visible in your feed. Note that this is much faster
# than the 'everything' command. To specify the number of posts to go through in
# the feed, pass the '-p <number of posts>' option; the default is 200.
instarchive feed
```

By default, the archive is located at the `instarchive` directory under the
home directory of the current OS user. This location can be changed by passing
the `-d <path to archive directory>` option to `instarchive`.

Run `instarchive [optional command name] --help` for usage information.

## Disclaimer

As with Instaloader itself, Instarchive is independent of and unsupported by
Instagram. Use at your own risk, and be wary of ratelimits.
