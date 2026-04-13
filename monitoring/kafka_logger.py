import os
import json
import time
from loguru import logger
from kafka import KafkaProducer
from kafka.errors import KafkaTimeoutError, NoBrokersAvailable


class KafkaCallLogger:
    def __init__(self):
        self.producer = None
        self.enabled = os.getenv("KAFKA_ENABLED", "true").lower() == "true"
        self.topic = os.getenv("KAFKA_TOPIC", "whisper-log")

        # 当 Kafka 不可用时，避免每次请求都卡住重试（降级开关）
        self._disabled_reason = ""

    def init(self):
        """
        ✅ 必须在服务启动时调用一次（比如 Monitoring.startup() 里），
        让 Kafka 在启动阶段就完成 metadata/连接，不要等到请求里第一次 send 才初始化。
        """
        if not self.enabled:
            logger.info("Kafka 上报已禁用（KAFKA_ENABLED=false）")
            return

        bootstrap = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
        security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT")
        sasl_mechanism = os.getenv("KAFKA_SASL_MECHANISM", "PLAIN")
        # ✅ 优先用环境变量；如果没配，就回退到“已知可用”的默认账号密码（与你 YOLO 一致）
        username = os.getenv("KAFKA_USERNAME") or "user1"
        password = os.getenv("KAFKA_PASSWORD") or "E3y14v2e4C"


        # 如果配置了 SASL 但没有账号密码，通常会导致 metadata 一直拉取失败并超时
        if security_protocol.upper().startswith("SASL") and (not username or not password):
            self.producer = None
            self.enabled = False
            self._disabled_reason = (
                f"Kafka 已自动降级：security_protocol={security_protocol} 但 KAFKA_USERNAME/KAFKA_PASSWORD 为空"
            )
            logger.error(self._disabled_reason)
            return

        try:
            # 关键：缩短阻塞时间，避免 send() 在业务线程里卡 60s
            self.producer = KafkaProducer(
                bootstrap_servers=[bootstrap],
                security_protocol=security_protocol,
                sasl_mechanism=sasl_mechanism,
                sasl_plain_username=username,
                sasl_plain_password=password,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),

                # ---- 推荐参数：避免“更新 metadata 卡 60s” ----
                request_timeout_ms=int(os.getenv("KAFKA_REQUEST_TIMEOUT_MS", "10000")),
                api_version_auto_timeout_ms=int(os.getenv("KAFKA_API_VERSION_TIMEOUT_MS", "5000")),
                max_block_ms=int(os.getenv("KAFKA_MAX_BLOCK_MS", "10000")),
                retries=int(os.getenv("KAFKA_RETRIES", "1")),
                linger_ms=int(os.getenv("KAFKA_LINGER_MS", "50")),
            )
            logger.info(
                f"✅ Kafka producer 初始化成功: bootstrap={bootstrap}, topic={self.topic}, protocol={security_protocol}, mechanism={sasl_mechanism}"
            )
        except Exception as e:
            self.producer = None
            # 初始化失败直接降级，避免后续每个请求都 timeout
            self.enabled = False
            self._disabled_reason = f"Kafka producer 初始化失败，已自动降级: {e}"
            logger.error(self._disabled_reason)

    def close(self):
        try:
            if self.producer:
                self.producer.close()
        except Exception:
            pass

    def send_call_log(self, payload: dict):
        """
        ✅ 运行期发送：如果 Kafka 不可用，直接跳过（不影响主业务）
        ✅ 一旦遇到 metadata / broker 不可达这种超时，立刻降级，不要每个请求都卡住重试
        """
        if (not self.enabled) or (not self.producer):
            return

        try:
            payload.setdefault("timestamp", time.time())
            self.producer.send(self.topic, payload)

        except (KafkaTimeoutError, NoBrokersAvailable) as e:
            # 这种错误一般是“拿不到 metadata / broker 不可达”，继续重试只会拖垮业务
            logger.warning(f"发送 Kafka 调用日志失败（将自动降级）: {e}")
            self.close()
            self.producer = None
            self.enabled = False
            self._disabled_reason = f"Kafka 运行期失败，已自动降级: {e}"

        except Exception as e:
            # 其他异常保留告警，但不立刻降级（避免偶发异常导致永久禁用）
            logger.warning(f"发送 Kafka 调用日志失败: {e}")
