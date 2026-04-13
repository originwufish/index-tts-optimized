# /home/wu/whisper/monitoring/core.py
import time
from loguru import logger
from typing import Optional, Dict

from prometheus_client import (
    Gauge,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# -------- Optional imports --------
try:
    from flask import Flask, request
    _HAS_FLASK = True
except Exception:
    _HAS_FLASK = False
    Flask = None

try:
    from fastapi import FastAPI, Request as FastAPIRequest
    from fastapi.responses import Response as FastAPIResponse
    _HAS_FASTAPI = True
except Exception:
    _HAS_FASTAPI = False
    FastAPI = None


from .gpu import GPUMonitor
from .kafka_logger import KafkaCallLogger


class Monitoring:
    """
    通用监控模块（Flask + FastAPI 兼容）
    """

    def __init__(self, service_name: str, service_id: str, use_gpu: bool = False):
        self.service_name = service_name
        self.service_id = service_id
        self.use_gpu = use_gpu

        self.gpu_monitor = GPUMonitor()
        self.kafka = KafkaCallLogger()

        # GPU
        self.CUDA_AVAILABLE = Gauge("cuda_available", "Whether CUDA is available (1=yes,0=no)")
        self.GPU_MEMORY_USED = Gauge("gpu_memory_used_bytes", "GPU memory used in bytes", ["device"])
        self.GPU_MEMORY_TOTAL = Gauge("gpu_memory_total_bytes", "Total GPU memory in bytes", ["device"])

        # HTTP
        self.HTTP_INPROGRESS = Gauge("http_requests_inprogress", "In-progress HTTP requests",
                                     ["method", "endpoint"])

        self.HTTP_REQUESTS_TOTAL = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "http_status"],
        )

        self.HTTP_REQUEST_LATENCY = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds",
            ["method", "endpoint"],
        )

    # =========================================================
    # 🔹 自动适配入口
    # =========================================================
    def attach(self, app, metrics_path: str = "/metrics"):
        """
        自动识别是 Flask 还是 FastAPI
        """
        if _HAS_FLASK and isinstance(app, Flask):
            logger.info("检测到 Flask 应用，使用 attach_flask()")
            return self.attach_flask(app, metrics_path)

        if _HAS_FASTAPI and isinstance(app, FastAPI):
            logger.info("检测到 FastAPI 应用，使用 attach_fastapi()")
            return self.attach_fastapi(app, metrics_path)

        raise TypeError(
            "❌ attach(app) 只支持 Flask 或 FastAPI 实例，"
            "请确认你传入的是 app 对象"
        )

    # =========================================================
    # Flask 适配
    # =========================================================
    def attach_flask(self, app, metrics_path="/metrics"):
        if not _HAS_FLASK:
            logger.warning("Flask 未安装，attach_flask() 跳过")
            return

        @app.route(metrics_path, methods=["GET"])
        def metrics():
            return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

        @app.before_request
        def _before():
            endpoint = request.url_rule.rule if request.url_rule else request.path
            method = request.method
            request._mon_start = time.time()
            self.HTTP_INPROGRESS.labels(method=method, endpoint=endpoint).inc()

        @app.after_request
        def _after(response):
            endpoint = request.url_rule.rule if request.url_rule else request.path
            method = request.method
            status = str(response.status_code)

            start = getattr(request, "_mon_start", None)
            if start:
                self.HTTP_REQUEST_LATENCY.labels(method=method, endpoint=endpoint)\
                    .observe(time.time() - start)

            self.HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, http_status=status).inc()
            self.HTTP_INPROGRESS.labels(method=method, endpoint=endpoint).dec()
            return response

        logger.info(f"✅ Prometheus metrics (Flask) 已挂载: {metrics_path}")

    # =========================================================
    # FastAPI 适配
    # =========================================================
    def attach_fastapi(self, app, metrics_path="/metrics"):
        if not _HAS_FASTAPI:
            logger.warning("FastAPI 未安装，attach_fastapi() 跳过")
            return

        @app.get(metrics_path)
        async def metrics():
            return FastAPIResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

        @app.middleware("http")
        async def monitor(request: FastAPIRequest, call_next):
            route = request.scope.get("route")
            endpoint = getattr(route, "path_template", request.url.path)
            method = request.method
            start = time.time()

            self.HTTP_INPROGRESS.labels(method=method, endpoint=endpoint).inc()

            try:
                response = await call_next(request)
                status = str(response.status_code)
            except Exception:
                status = "500"
                raise
            finally:
                self.HTTP_REQUEST_LATENCY.labels(method=method, endpoint=endpoint)\
                    .observe(time.time() - start)

                self.HTTP_REQUESTS_TOTAL.labels(
                    method=method, endpoint=endpoint, http_status=status
                ).inc()

                self.HTTP_INPROGRESS.labels(method=method, endpoint=endpoint).dec()

            return response

        logger.info(f"✅ Prometheus metrics (FastAPI) 已挂载: {metrics_path}")

    # =========================================================
    # 生命周期
    # =========================================================
    def startup(self):
        if not self.use_gpu:
            self.CUDA_AVAILABLE.set(0)
        else:
            self.gpu_monitor.init()
            if self.gpu_monitor.available:
                self.CUDA_AVAILABLE.set(1)
                for i in range(self.gpu_monitor.device_count()):
                    self.GPU_MEMORY_TOTAL.labels(device=str(i)).set(self.gpu_monitor.total_memory(i))
            else:
                self.CUDA_AVAILABLE.set(0)

        self.kafka.init()

    def shutdown(self):
        self.kafka.close()
        self.gpu_monitor.shutdown()

    def update_gpu_metrics(self):
        if not self.use_gpu or not self.gpu_monitor.available:
            return
        for i in range(self.gpu_monitor.device_count()):
            self.GPU_MEMORY_USED.labels(device=str(i)).set(self.gpu_monitor.used_memory(i))

    # =========================================================
    # Kafka Call Log
    # =========================================================
    def send_call_log(self, endpoint, duration_sec, filename="", extra: Optional[Dict] = None):
        payload = {
            "service_name": self.service_name,
            "service_id": self.service_id,
            "endpoint": endpoint,
            "duration_sec": round(duration_sec, 3),
            "filename": filename,
            "ts": time.time(),
        }
        if extra:
            payload.update(extra)
        self.kafka.send_call_log(payload)
