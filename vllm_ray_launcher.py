import ray
import os
import subprocess
import sys
import time

# ==========================================
# vLLM on Ray Launcher
# This script wraps the vLLM server in a Ray Actor
# and enables Ray as the distributed execution backend.
# ==========================================

@ray.remote(num_gpus=1)
class VLLMRayActor:
    def __init__(self, model_path: str, model_name: str, port: int = 8000):
        self.model_path = model_path
        self.model_name = model_name
        self.port = port
        self.process = None

    def start(self):
        """Start vLLM OpenAI API Server and integrate with Ray"""
        # Optimization parameters for RTX GPUs
        cmd = [
            sys.executable, "-m", "vllm.entrypoints.openai.api_server",
            "--model", self.model_path,
            "--served-model-name", self.model_name,
            "--quantization", "gptq",
            "--gpu-memory-utilization", "0.80", # Reserve 20% VRAM for other Ray tasks or system
            "--max-model-len", "8192",
            "--max-num-seqs", "5",
            "--port", str(self.port),
            "--trust-remote-code",
            "--enforce-eager",
            "--distributed-executor-backend", "ray"  # Integration with Ray
        ]
        
        print(f"[Ray Actor] Starting vLLM server...")
        print(f"Command: {' '.join(cmd)}")
        
        # Launch with subprocess to allow the Actor to monitor the process
        self.process = subprocess.Popen(cmd)
        return f"vLLM server started in Ray cluster (PID: {self.process.pid}, Port: {self.port})"

    def check_health(self):
        """Check if the vLLM process is still running"""
        if self.process and self.process.poll() is None:
            return True
        return False

    def stop(self):
        """Stop the server"""
        if self.process:
            print("Stopping vLLM server...")
            self.process.terminate()
            self.process.wait()
            return "vLLM Stopped"
        return "No process running"

def main():
    # 1. Initialize Ray (if not already started)
    if not ray.is_initialized():
        print("Initializing Ray...")
        ray.init(ignore_reinit_error=True)

    # 2. Set model path
    # Read from environment variable or use default path
    model_path = os.getenv("DEFAULT_LOCAL_MODEL_PATH")
    if not model_path:
        model_path = os.path.abspath(os.path.expanduser("~/models/Qwen2.5-7B-GPTQ"))
    
    model_name = "qwen2.5-7b"
    
    # 3. Create and start Ray Actor
    # Define as a named actor for access by other Kuugen components
    try:
        vllm_actor = VLLMRayActor.options(
            name="vllm_service", 
            get_if_exists=True
        ).remote(model_path, model_name)
        
        result = ray.get(vllm_actor.start.remote())
        print(result)

        print("\nvLLM is now running as a Ray Actor.")
        print("You can monitor resource usage via the Ray Dashboard.")
        print("Press Ctrl+C to stop the server and shutdown Ray.")

        # 4. Monitoring loop
        while True:
            if not ray.get(vllm_actor.check_health.remote()):
                print("vLLM server terminated unexpectedly, attempting restart...")
                ray.get(vllm_actor.start.remote())
            time.sleep(30)

    except KeyboardInterrupt:
        print("\nShutdown signal received...")
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        # Cleanup
        try:
            actor = ray.get_actor("vllm_service")
            ray.get(actor.stop.remote())
        except:
            pass
        ray.shutdown()

if __name__ == "__main__":
    main()
