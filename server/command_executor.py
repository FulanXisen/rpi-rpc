import subprocess
import shlex
from typing import Tuple

class CommandExecutor:
    """
    执行单次命令的处理器
    
    特性：
    - 每次调用创建独立进程
    - 不保持任何状态
    - 适合执行独立任务
    """
    
    @staticmethod
    def execute_command(command: str) -> Tuple[int, str, str]:
        """
        执行单个命令并返回结果
        
        参数:
            command: 要执行的shell命令字符串
            
        返回:
            元组 (return_code, stdout, stderr)
        """
        try:
            process = subprocess.Popen(
                shlex.split(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False
            )
            stdout, stderr = process.communicate(timeout=60)
            return process.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            process.kill()
            return -1, "", "Command timed out after 60 seconds"
        except Exception as e:
            return -1, "", f"Command execution failed: {str(e)}"

