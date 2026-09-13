import os
from huggingface_hub import snapshot_download

# Set model name and storage path
model_id = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
local_dir = os.path.expanduser("~/models/Qwen/Qwen2.5-Coder-7B-Instruct-AWQ")

print(f"Starting model download: {model_id}")
print(f"Storage path: {local_dir}")

try:
    # Execute download
    path = snapshot_download(
        repo_id=model_id,
        local_dir=local_dir,
        local_dir_use_symlinks=False,  # Download physical files directly
        revision="main",                # Download main branch
        ignore_patterns=["*.msgpack", "*.h5"] # Ignore unnecessary formats to save space
    )
    print(f"\nDownload complete! Model stored at: {path}")
    
except Exception as e:
    print(f"\nDownload error: {e}")
