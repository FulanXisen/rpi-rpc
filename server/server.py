import select
import grpc
import signal
import os 
import subprocess
from loguru import logger
from concurrent import futures
from proto import command_pb2, command_pb2_grpc

NOT_EXIT=65537

def popen(command):
    process = subprocess.Popen(
        ["bash", "-c", f"gstdbuf -o0 -e0 {command}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
        text=True,
        shell=False,
        env=os.environ,
    )
    return process

class Commander(command_pb2_grpc.CommandServicer):
    def Execute(self, request, context):
        command = request.command
        timeout = 60 
        returncode = -1 
        stdout = ""
        try:
            process = popen(command) 
            stdout, stderr = process.communicate(timeout=timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            try:
                process # type: ignore 
            except NameError:
                pass 
            else:
                process.kill() # type: ignore 
            finally:
                stderr = f"Command timed out after {timeout} seconds"
        except Exception as e:
            stderr = f"Command execution failed: {str(e)}"
        
        return command_pb2.CommandResponse(returncode=returncode, stdout=stdout, stderr=stderr)
    def ExecuteStream(self, request, context):
        command = request.command
        timeout = 60 
        returncode = -1 
        stdout = ""
        try:
            process = subprocess.Popen(
                ["bash", "-c", f"gstdbuf -o0 -e0 {command}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid,
                env=os.environ,
            )
            while True:
                # 检测客户端是否断开
                if context.is_active() == False:
                    logger.info("客户端已断开，终止bash -c进程")
                    os.killpg(os.getpgid(process.pid), signal.SIGINT)  # 终止整个进程组
                    break
                readable,_,_ = select.select([process.stdout, process.stderr], [], [], 0.1)
                if process.poll() is not None:
                    logger.debug("poll is not None")
                    break 
                if not readable:
                    logger.debug("not readable")
                    continue
                for stream in readable:
                    logger.debug(f"stream {stream}")
                    if stream is process.stdout:
                        src = "stdout"
                    else:
                        src = "stderr"
                    while True:
                        line = stream.readline()
                        logger.debug(f"line {line}")
                        logger.debug(f"{line == None}, {line == ''}, {line == ' '}")
                        if line and line != '':
                            if context.is_active() != False:
                                response = command_pb2.CommandResponse(returncode=NOT_EXIT, stdout=line if src=="stdout" else "", stderr=line if src=="stderr" else "")
                                yield response
                            else:
                                break
                        else:
                            break
            logger.debug("Over Baby!")
            stdout, stderr = process.communicate(timeout=timeout)
            returncode = process.returncode

        except subprocess.TimeoutExpired:
            logger.debug("TimeoutExpired")
            try:
                logger.debug("try")
                process # type: ignore 
            except NameError:
                logger.debug("NameError")
                pass 
            else:
                logger.debug("process.kill")
                process.kill() # type: ignore 
            finally:
                logger.debug("finally")
                stderr = f"Command timed out after {timeout} seconds"
        except Exception as e:
            logger.debug(f"exception {str(e)}")
            stderr = f"Command execution failed: {str(e)}"
        
        command_pb2.CommandResponse(returncode=returncode, stdout=stdout, stderr=stderr)
        yield
    pass 

@logger.catch()
def serve():
    port = "50051"
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    command_pb2_grpc.add_CommandServicer_to_server(Commander(), server)
    server.add_insecure_port("[::]:" + port)
    server.start()
    print("Server started, listening on " + port)
    server.wait_for_termination()

serve()
