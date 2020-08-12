# How to release a new version ?

The release process of Mixer is handled with CI/CD and based on git tags. Each tag with a name `v{major}.{minor}.{bugfix}` is considered to be a release tag and should trigger the release job of the CI/CD.

The preliminary steps for creating a release `v{major}.{minor}.{bugfix}` are : 
- check that the tag `v{major}.{minor}.{bugfix}` does not exist
- ensure all the changes have been committed
- edit `CHANGELOG.md` to add a section describing the release and starting with `# <major>.<minor>.<bugfix>`
- commit with a message like `doc:update CHANGELOG.md for <major>.<minor>.<bugfix>`

Do not add the tag manually, instead run the script:

```bash
python -m extra.prepare_release <major> <minor> <bugfix>
```

The script will inject the new version number in the addon `bl_info` dictionnary and tag the commit.

You can then push the tag:

```bash
# Push the branch
git push
# Push the tag
git push --tags
```

Then watch your pipeline on Gitlab and wait for the release notes to appear on the release page.

## What if I did a mistake ?

It may happen. In that case just go to gitlab and remove the tag. It will also remove the release.

In your local repository manually delete the tag.
