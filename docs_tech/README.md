Tempmorary directory for dev/architecture/API documentation

```
cd docs_tech
sphinx-apidoc -f -o . ..\mixer ../mixer/bl_*.py
make html
```