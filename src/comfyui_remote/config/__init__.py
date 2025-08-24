if __name__ == "__main__":
    from comfyui_remote.config.manager import ConfigManager

    # Optional: ensure COMFY_CONFIG points to your controller
    # import os; os.environ["COMFY_CONFIG"] = r"E:\comfyui\comfyui-remote\src\comfyui_remote\config\defaults\default.json"

    mgr = ConfigManager()
    cfg = mgr.finalize()

    print("\n--- Which files were merged ---")
    print(mgr.debug_controller_sources())

    print("\n--- Merged Comfy YAML (expanded) ---")
    print(mgr.debug_comfy_yaml_text(expand=True))  # <-- merged YAML side

    print("\n--- Expanded ComfyConfig snapshot (server/io/paths/env) ---")
    print(mgr.debug_expanded_yaml_text(cfg))  # <-- resolved runtime view

