# How to release a new version ?

The release process of Mixer is handled with CI/CD and based on git tags. Each tag with a name `v{major}.{minor}.{bugfix}` is considered to be a release tag and should trigger the release job of the CI/CD.

You should not add such tag manually, instead run the script:

```bash
python -m extra.prepare_release <major> <minor> <bugfix>
```

For it to succeed:

- You should have commited all your changes
- You should have added a section describing the release and starting with `# <major>.<minor>.<bugfix>` in `CHANGELOG.md`
- The tag `v{major}.{minor}.{bugfix}` should not already exists

If all these requirements are met, then the script will inject the new version number in the addon `bl_info` dictionnary and tag the commit.

You can then push the tag:

```bash
git push # Push the branch
git push --tags # Push the tag
```

Then watch your pipeline on Gitlab and wait for the release notes to appear on the release page.

## What if I did a mistake ?

It may happen. In that case just go to gitlab and remove the tag. It will also remove the release.

In your local repository manually delete the tag.
