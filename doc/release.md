# How to release a new version ?

The release process of Mixer is handled with CI/CD and based on git tags. The tags that are considered to be a release tag and should trigger the release job of the CI/CD are :

- `v{major}.{minor}.{bugfix}`
- `v{major}.{minor}.{bugfix}-{prerelease}`
- `v{major}.{minor}.{bugfix}+{build}`
- `v{major}.{minor}.{bugfix}-{prerelease}+{build}`

The preliminary steps for creating a release tagged as described above are :

- check that the tag does not exist
- ensure all the changes have been committed
- edit `CHANGELOG.md` to add a section describing the release and starting with a comment line containing the release tag
- commit with a message like `doc:update CHANGELOG.md for <release tag>`

Do not add the tag manually, instead run the script as follows:

```bash
python -m extra.prepare_release <major> <minor> <bugfix> [--prerelease <prerelease>] [--build <build>]
```

The script will inject the new version number in the addon `bl_info` dictionary and tag the commit.

You can then push the tag:

```bash
# Push the branch
git push
# Push the tag
git push --tags
```

Then watch your pipeline on Gitlab and wait for the release notes to appear on the release page.

## What if I did a mistake ?

It may happen. In that case just go to Gitlab and remove the tag. It will also remove the release.

In your local repository manually delete the tag.
