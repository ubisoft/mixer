Documenting Mixer TODO
========================

Mixer documentation is written in reStructuredText, generated with `Sphinx <https://www.sphinx-doc.org/>`_ and hosted at `<https://mixer-github.readthedocs.io/en/latest/>`_.


Generating the documentation
----------------------------

Install the development tools:

::

   pip install -r requirements-dev

Generate the documentation:

::

   cd mixer/docs
   make html

The resulting documentation is in the ``docs/_build`` folder, the index file being ``docs/_build/html/index.html``.

The `reStructuredText VSCode extension <https://github.com/vscode-restructuredtext/vscode-restructuredtext>`_ provides previewing in VSCode with your favorite theme.
