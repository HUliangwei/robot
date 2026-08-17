def get_available_devices():
    return [0]

def egl_probe_egl():
    return False

def egl_probe_glx():
    return False

def probe():
    return {'egl': False, 'glx': False, 'devices': [0]}
