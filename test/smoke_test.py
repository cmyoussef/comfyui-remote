import json, time
from comfyui_remote.executors.api_executor import ComfyConnector

class _Sig:
    def emit(self, *_args, **_kwargs): pass

def never(): return False

payload_path = r"E:\comfyui\test\smoke.json"
payload = json.load(open(payload_path, "r"))

cc = ComfyConnector(
    json_file=payload,
    comfyui_version=None,
    current_iteration=1,
    total_iterations=1,
    is_interrupted=never,
    progress_signal=_Sig(),
)

# Run once
cc.generate_images(payload, 1, never)

# Clean shutdown
cc.kill_api()
print("SMOKE OK")
