try:
    import ptvsd

    def wait_for_debugger():
        # 5678 is the default attach port in the VS Code debug configurations
        print("Waiting for debugger attach")
        ptvsd.enable_attach(address=('localhost', 5678), redirect_output=True)
        ptvsd.wait_for_attach()
        breakpoint()
except ImportError:
    def wait_for_debugger():
        pass
