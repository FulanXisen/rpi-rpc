import os
import queue
import threading
import time
from multiprocessing import Queue
from typing import Dict, List, Optional, Tuple

from loguru import logger

from src.impl import rpc_bg


class RpcStreamIOMonitor:
    """
    监控流式数据并支持多关键词异步检查。
    PipedRpcStreamProcess 继承自 multiprocessing.Process，通过队列传递数据。
    """

    @logger.catch
    def __init__(self, p, file_path: Optional[str] = None):
        """
        :param p: PipedRpcStreamProcess 实例，需实现 msgq() 方法返回 Queue
        :param file_path: 可选，将接收到的数据实时写入文件
        """
        self.p = p
        self.tasks: Dict[int, dict] = {}  # 存储所有检查任务 {task_id: {result, lines}}
        self.lock = threading.Lock()  # 线程安全锁
        self.task_id_counter = 0  # 任务ID生成器
        self.running = True  # 控制后台线程退出
        self.file_path = file_path
        self.file = None

        if self.file_path:
            if os.path.dirname(self.file_path):
                os.makedirs(os.path.dirname(self.file_path))
            self.file = open(self.file_path, "a", encoding="utf-8", errors="ignore")

        # 启动后台读取线程
        self.thread = threading.Thread(target=self._read_stream, daemon=True)
        self.thread.start()

    def _read_stream(self):
        """持续从队列读取数据并分发给任务"""
        q: Queue = self.p.msgq()
        while self.running:
            try:
                line = q.get(timeout=1)  # 阻塞式读取，超时1秒检查 running 状态

                # 处理可能的非字符串数据和乱码
                try:
                    if not isinstance(line, str):
                        line = str(line)
                    line = line.strip()
                except Exception:
                    continue  # 跳过无法处理的乱码数据

                logger.debug(f"read: {line}")
                # 写入文件
                if self.file:
                    try:
                        self.file.write(line + "\n")
                        self.file.flush()
                    except (IOError, UnicodeError):
                        pass

                with self.lock:
                    for task in self.tasks.values():
                        task["lines"].append(line)  # 记录当前行到所有任务

            except queue.Empty:
                continue
            except (AttributeError, ValueError, EOFError):
                break  # 队列异常或进程终止

    def assert_keywords(self, keywords: List[str], timeout: float) -> int:
        """
        添加关键词检查任务
        :param keywords: 需要匹配的关键词列表
        :param timeout: 超时时间（秒）
        :return: task_id 用于后续查询结果
        """
        task_id = self._generate_task_id()
        result = {
            "keywords": keywords,
            "timeout": timeout,
            "found": [False] * len(keywords),
            "matched_lines": [None] * len(keywords),
            "start_time": time.time(),
            "completed": False,
            "condition": threading.Condition(),  # 用于等待结果
        }

        with self.lock:
            self.tasks[task_id] = {"result": result, "lines": []}

        # 启动监控线程
        threading.Thread(
            target=self._monitor_task,
            args=(task_id,),
            daemon=True,
        ).start()

        return task_id

    def result(
        self, task_id: int, wait: bool = False
    ) -> Optional[Tuple[bool, List[bool], List[Optional[str]]]]:
        """
        获取任务结果
        :param task_id: 任务ID
        :param wait: 是否等待任务完成
        :return: (是否全部匹配, 每个关键词匹配状态, 每个关键词匹配的行)
        """
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return None

        result = task["result"]

        if wait and not result["completed"]:
            with result["condition"]:
                result["condition"].wait(
                    result["timeout"] - (time.time() - result["start_time"])
                )

        with self.lock:
            if not result["completed"]:
                return None

            all_matched = all(result["found"])
            status_list = result["found"].copy()
            lines_list = result["matched_lines"].copy()

            return (all_matched, status_list, lines_list)

    def _monitor_task(self, task_id: int):
        """监控任务超时和关键词匹配"""
        start_time = time.time()
        while self.running:
            with self.lock:
                task = self.tasks.get(task_id)
                if not task:
                    return

                result = task["result"]
                elapsed = time.time() - start_time

                if elapsed > result["timeout"] or all(result["found"]):
                    result["completed"] = True
                    with result["condition"]:
                        result["condition"].notify_all()
                    self._remove_task(task_id)
                    return

                # 检查每个关键词是否匹配
                for i, keyword in enumerate(result["keywords"]):
                    if result["found"][i]:
                        continue

                    for line in task["lines"]:
                        if keyword in line:
                            result["found"][i] = True
                            result["matched_lines"][i] = line
                            break

            time.sleep(0.05)

    def _remove_task(self, task_id: int):
        """安全移除任务"""
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]

    def _generate_task_id(self) -> int:
        """生成唯一递增ID"""
        with self.lock:
            self.task_id_counter += 1
            return self.task_id_counter

    def stop(self):
        """停止监控器并清理资源"""
        self.running = False
        if self.thread.is_alive():
            logger.debug("join read")
            self.thread.join()

        if self.file:
            try:
                self.file.close()
            except:
                pass

        with self.lock:
            # 通知所有等待的任务
            for task in self.tasks.values():
                logger.debug(f"join task {task}")
                task["result"]["completed"] = True
                with task["result"]["condition"]:
                    task["result"]["condition"].notify_all()
            self.tasks.clear()


if __name__ == "__main__":
    # p = rpc_bg("python3 $HOME/like/rpi-grpc/apps/test_env.py")
    p = rpc_bg("ls -la")
    assert p.is_alive()
    monitor = RpcStreamIOMonitor(p, "log.log")
    task_id = monitor.assert_keywords(["fanyx"], timeout=2)
    ret = monitor.result(task_id)
    print(ret)
    time.sleep(2)
    monitor.stop()
