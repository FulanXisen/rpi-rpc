import os
import pty
import select
import threading
from typing import Dict, Tuple, Optional
import logging

from pprint import pp

from loguru import logger 


class SessionManager:
    """
    交互式会话管理器
    
    特性：
    - 为每个客户端维护一个持久的bash进程
    - 保持工作目录、环境变量等状态
    - 使用伪终端(pty)模拟真实终端行为
    - 线程安全设计
    """
    
    def __init__(self):
        # 使用线程锁保证会话操作的线程安全
        self._lock = threading.Lock()
        # 存储所有活跃会话 {session_id: session_data}
        self._sessions: Dict[str, dict] = {}
        
    def create_session(self) -> str:
        """
        创建一个新的交互式shell会话
        
        返回:
            新创建会话的唯一ID
            
        异常:
            OSError: 如果创建进程失败
        """
        # 创建伪终端主从设备对
        master_fd, slave_fd = pty.openpty()
        
        try:
            # 创建子进程
            pid = os.fork()
            
            if pid == 0:  # 子进程
                # 创建新的会话组
                os.setsid()
                
                # 将伪终端从设备作为子进程的标准IO
                os.dup2(slave_fd, 0)  # 标准输入
                os.dup2(slave_fd, 1)  # 标准输出
                os.dup2(slave_fd, 2)  # 标准错误
                
                # 关闭不需要的文件描述符
                os.close(master_fd)
                
                # 启动交互式bash shell
                os.execlp("bash", "bash", "--norc", "-i")
                os._exit(0)  # 如果execlp失败
                
            else:  # 父进程
                os.close(slave_fd)
                
                # 生成唯一会话ID
                session_id = f"session_{pid}"
                
                with self._lock:
                    self._sessions[session_id] = {
                        'pid': pid,
                        'master_fd': master_fd,
                        'active': True
                    }
                
                logging.info(f"Created new session {session_id}")
                return session_id
                
        except OSError as e:
            os.close(master_fd)
            os.close(slave_fd)
            logging.error(f"Failed to create session: {str(e)}")
            raise
            
    def execute_in_session(self, session_id: str, command: str) -> Tuple[int, str, str]:
        """
        在指定会话中执行命令
        
        参数:
            session_id: 要操作的会话ID
            command: 要执行的命令
            
        返回:
            元组 (return_code, stdout, stderr)
            
        异常:
            ValueError: 如果会话不存在
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or not session['active']:
                raise ValueError(f"Session {session_id} not found or inactive")
            
            master_fd = session['master_fd']
            
        try:
            # 发送命令到伪终端(添加换行符以执行)
            os.write(master_fd, f"{command}\n".encode('utf-8'))
            
            # 读取命令输出
            stdout_buffer = b''
            while True:
                # 使用select等待数据可读，超时500ms
                rlist, _, _ = select.select([master_fd], [], [], 0.5)
                if not rlist:  # 超时
                    logger.debug("select stdout timeout")
                    break
                    
                try:
                    data = os.read(master_fd, 1024)
                    if not data:  # EOF
                        break
                    stdout_buffer += data
                except (OSError, InterruptedError):
                    break
            
            # 获取命令返回码(通过执行特殊命令)
            os.write(master_fd, b"echo $?\n")
            return_code_buffer = b''
            while True:
                rlist, _, _ = select.select([master_fd], [], [], 0.1)
                if not rlist:
                    logger.debug("select returncode timeout")
                    break
                try:
                    data = os.read(master_fd, 16)
                    if not data:
                        break
                    return_code_buffer += data
                except (OSError, InterruptedError):
                    break
            
            # 解析返回码(从输出中提取最后一行)
            try:
                return_code = int(return_code_buffer.strip().split(b'\r\n')[-1])
            except (ValueError, IndexError):
                return_code = -1
            
            # 处理输出 - 移除命令回显和返回码行
            stdout_lines = stdout_buffer.split(b'\r\n')
            if len(stdout_lines) > 1:
                stdout = b'\r\n'.join(stdout_lines[1:-1]).decode('utf-8', errors='replace')
            else:
                stdout = ""
            
            return return_code, stdout, ""
            
        except Exception as e:
            logging.error(f"Error executing in session {session_id}: {str(e)}")
            return -1, "", str(e)
            
    def close_session(self, session_id: str):
        """
        关闭指定会话并清理资源
        
        参数:
            session_id: 要关闭的会话ID
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return
                
        try:
            # 关闭伪终端主设备
            os.close(session['master_fd'])
            # 终止子进程
            os.kill(session['pid'], 9)
            logging.info(f"Closed session {session_id}")
        except ProcessLookupError:
            pass  # 进程已经退出
        except OSError as e:
            logging.warning(f"Error closing session {session_id}: {str(e)}")
            
    def cleanup_all(self):
        """清理所有活跃会话"""
        with self._lock:
            for session_id in list(self._sessions.keys()):
                self.close_session(session_id)

@logger.catch
def main():
    session_maneger = SessionManager()
    id = session_maneger.create_session()
    pp(id)
    retCode, stdOut, stdErr = session_maneger.execute_in_session(id, "cd ~/")
    pp(retCode)
    pp(stdOut)
    pp(stdErr)
    retCode, stdOut, stdErr = session_maneger.execute_in_session(id, "sleep 3")
    pp(retCode)
    pp(stdOut)

if __name__ == "__main__":
    main()    
