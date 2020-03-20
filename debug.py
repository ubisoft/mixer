try:
    import ptvsd

    def wait_for_debugger(port):
        # 5678 is the default attach port in the VS Code debug configurations
        print("Waiting for debugger attach")
        enable_attach()
        ptvsd.wait_for_attach()
        breakpoint()

    def enable_attach(port=5678):
        ptvsd.enable_attach(address=('localhost', port), redirect_output=True)

except ImportError:
    def wait_for_debugger():
        pass
