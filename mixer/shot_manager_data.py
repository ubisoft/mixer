class ShotManager:
    def __init__(self):
        self.current_take_name = ""
        self.current_shot_index = -1
        self.montage_mode = None
        self.shots = []


class Shot:
    def __init__(self):
        self.name = ""
        self.camera_name = ""
        self.start = 0
        self.end = 0
        self.enabled = True
