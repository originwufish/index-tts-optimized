from loguru import logger

class GPUMonitor:
    def __init__(self):
        self.available = False
        self.pynvml = None

    def init(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self.pynvml = pynvml
            self.available = True
            logger.info("✅ pynvml 初始化成功，支持 GPU 显存监控")
        except Exception as e:
            self.available = False
            logger.warning(f"⚠️ pynvml 不可用（可能无 NVIDIA GPU）: {e}")

    def shutdown(self):
        if not self.available or not self.pynvml:
            return
        try:
            self.pynvml.nvmlShutdown()
        except Exception:
            pass

    def device_count(self) -> int:
        if not self.available:
            return 0
        return self.pynvml.nvmlDeviceGetCount()

    def total_memory(self, idx: int) -> int:
        handle = self.pynvml.nvmlDeviceGetHandleByIndex(idx)
        mem = self.pynvml.nvmlDeviceGetMemoryInfo(handle)
        return int(mem.total)

    def used_memory(self, idx: int) -> int:
        handle = self.pynvml.nvmlDeviceGetHandleByIndex(idx)
        mem = self.pynvml.nvmlDeviceGetMemoryInfo(handle)
        return int(mem.used)
