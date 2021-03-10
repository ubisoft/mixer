Documenting Mixer
=================================

Mixer documentation is is written in ReStructuredText and hosted at `<https://mixer-github.readthedocs.io/en/latest/>`_.

Useful tools
------------

reStructuredText Cheat sheet:  `<https://docutils.sourceforge.io/docs/user/rst/quickref.html>`_

This VSCode extension provides previewing in VSCode with your favorite theme `<https://github.com/vscode-restructuredtext/vscode-restructuredtext>`_.

Generating the documentation
----------------------------
A local copy of the HTML documentation can be generated using Sphinx :

Install Sphinx and the readthedocs theme

::
   pip install sphinx
   pip install sphinx-rtd-theme

Generate the documentation:

::
   cd docs
   make html

The resulting documentation is in the ``docs/_build`` folder, the index file being ``docs/_build/html/index.html``.
