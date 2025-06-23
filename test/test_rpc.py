import os
import subprocess
import time

import pytest
from loguru import logger

from src.client import rpc, rpc_bg, rpc_echo_test

ADDR_PORT = os.environ.get("RPC_ADDR_PORT", "localhost:50051")


@pytest.mark.macos
@pytest.mark.rpi
def test_rpc():
    assert rpc_echo_test(ADDR_PORT)


@pytest.mark.macos
@pytest.mark.rpi
def test_echo_command():
    ret, out, err = rpc("echo 123", ADDR_PORT)
    assert ret == 0
    assert out.strip() == "123"


@pytest.mark.macos
@pytest.mark.rpi
def test_env_command():
    ret, out, err = rpc("echo $USER", ADDR_PORT)
    assert ret == 0


@pytest.mark.macos
def test_macos_play_music():
    p = rpc_bg("afplay ~/Music/本地音乐/5_20AM-soldier.flac", ADDR_PORT)
    time.sleep(5)
    cmd = "ps aux | grep afplay | grep -v grep"
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        assert bool(output.strip())
    except Exception as e:
        assert False
    p.stop()
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        assert not bool(output.strip())
    except Exception as e:
        assert True


@pytest.mark.macos
def test_macos_record_audio():
    home_dir = os.environ.get("HOME")
    file = f"{home_dir}/tmp/output.wav"
    if os.path.exists(file):
        os.remove(file)

    p = rpc_bg(f'ffmpeg -y -f avfoundation -i ":0" {file}', ADDR_PORT)
    time.sleep(4)
    cmd = "ps aux | grep ffmpeg | grep -v grep"
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        assert bool(output.strip())
    except Exception as e:
        assert False
    p.stop()
    assert os.path.exists(file)
    try:
        output = subprocess.check_output(cmd, shell=True, text=True)
        assert not bool(output.strip())
    except Exception as e:
        assert True


@pytest.mark.macos
def test_macos_play_and_record():
    p0 = rpc_bg("afplay ~/Music/本地音乐/5_20AM-soldier.flac", ADDR_PORT)

    home_dir = os.environ.get("HOME")
    file = f"{home_dir}/tmp/output.wav"
    if os.path.exists(file):
        os.remove(file)

    p1 = rpc_bg(f'ffmpeg -y -f avfoundation -i ":0" {file}', ADDR_PORT)
    time.sleep(2)
    cmd1 = "ps aux | grep ffmpeg | grep -v grep"
    try:
        output = subprocess.check_output(cmd1, shell=True, text=True)
        assert bool(output.strip())
    except Exception as e:
        logger.debug(f"{e}")
        assert False

    cmd0 = "ps aux | grep afplay | grep -v grep"
    try:
        output = subprocess.check_output(cmd0, shell=True, text=True)
        assert bool(output.strip())
    except Exception as e:
        logger.debug(f"{e}")
        assert False
    p1.stop()
    p0.stop()
    assert os.path.exists(file)
    try:
        output = subprocess.check_output(cmd0, shell=True, text=True)
        assert not bool(output.strip())
    except Exception as e:
        assert True
    assert os.path.exists(file)
    try:
        output = subprocess.check_output(cmd1, shell=True, text=True)
        assert not bool(output.strip())
    except Exception as e:
        assert True


@pytest.mark.rpi
def test_rpi_headphone_play_music():
    if ADDR_PORT != ADDR_PORT:
        return
    p = rpc_bg("ffmpeg -i $HOME/tmp/5_20.flac -f wav - | aplay", ADDR_PORT)
    time.sleep(2)
    cmd = "ps aux | grep aplay | grep -v grep"
    try:
        ret, out, err = rpc(cmd, ADDR_PORT)
        assert "aplay" in out
    except Exception as e:
        assert False
    p.stop()
    try:
        ret, out, err = rpc(cmd, ADDR_PORT)
        assert "aplay" not in out
    except Exception as e:
        assert True
