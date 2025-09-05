import platform
import os
import psutil
import argparse
import random
import ctypes
from ctypes.wintypes import HANDLE, DWORD, LARGE_INTEGER, BOOL
import tqdm
import subprocess
import sys


def is_admin(os_type=None):
    """
    检测当前用户是否具有管理员(root)权限
    
    参数:
        os_type: 操作系统类型 ('linux', 'windows' 或 None=自动检测)
    
    返回:
        bool: 如果是管理员/root权限返回True，否则返回False
    """
    if os_type is None:
        os_type = platform.system().lower()
    
    
    if os_type == 'Windows':
        return _is_admin_windows()
    elif os_type == 'Linux':  
        return _is_admin_unix()
    else:
        raise ValueError(f"不支持的OS类型: {os_type}")

def _is_admin_windows():
    """检测Windows管理员权限"""
    try:
        # 方法1: 使用ctypes检查管理员权限
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        # 方法2: 如果方法1失败，尝试其他方法
        try:
            # 尝试访问需要管理员权限的资源
            with open(r'C:\Windows\System32\config\system', 'r'):
                pass
            return True
        except:
            return False

def _is_admin_unix():
    """检测Unix-like系统(root)权限"""
    # 在Unix-like系统中，root用户的UID为0
    return os.geteuid() == 0

def hide_file(os_type, filepath):
    """
    在指定操作系统上隐藏文件（需要管理员权限）
    
    参数:
        os_type: 操作系统类型 ('linux' 或 'windows')
        filepath: 要隐藏的文件路径
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"文件不存在: {filepath}")
    
    if os_type.lower() == 'windows':
        return _hide_file_windows(filepath)
    elif os_type.lower() == 'linux':
        return _hide_file_linux(filepath)
    else:
        raise ValueError("不支持的OS类型，只支持 'windows' 或 'linux'")

def _hide_file_windows(filepath):
    """Windows系统下的文件隐藏实现"""
    try:
        # 设置文件属性为系统和隐藏（需要管理员权限）
        # FILE_ATTRIBUTE_SYSTEM = 0x4
        # FILE_ATTRIBUTE_HIDDEN = 0x2
        result = ctypes.windll.kernel32.SetFileAttributesW(filepath, 0x4 | 0x2)
        if not result:
            raise ctypes.WinError()
        return True
    except Exception as e:
        print(f"Windows隐藏失败: {e}")
        return False

def _hide_file_linux(filepath):
    """Linux系统下的文件隐藏实现"""
    try:
        # 先处理重命名（核心修改点）
        dirname, filename = os.path.split(filepath)
        if not filename.startswith('.'):
            new_path = os.path.join(dirname, '.' + filename)
            
            # 使用绝对路径确保权限
            abs_old = os.path.abspath(filepath)
            abs_new = os.path.abspath(new_path)
            
            os.rename(abs_old, abs_new)  # 先重命名
            filepath = abs_new  # 更新为新的绝对路径
        
        # 然后设置文件属性（在重命名后）
        # 使用绝对路径执行命令
        result = subprocess.run(
            ['chattr', '+i', filepath], 
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"chattr警告: {result.stderr}")
        
        # 尝试设置扩展属性
        try:
            subprocess.run(
                ['attr', '-s', 'hidden', '-V', '1', filepath],
                capture_output=True
            )
        except Exception:
            pass  # 忽略失败
            
        return True
    except Exception as e:
        print(f"Linux隐藏失败: {e}")
        try:
            dirname, filename = os.path.split(filepath)
            if not filename.startswith('.'):
                new_path = os.path.join(dirname, '.' + filename)
                os.rename(filepath, new_path)
        except:
            pass
        return False


def extend_file_size_linux(file_path, add_size):
    """
    扩展文件大小（Linux版本）
    
    参数:
        file_path: 文件路径
        new_size: 新的文件大小（字节）
    """
    # 获取当前文件大小
    current_size = os.path.getsize(file_path)
    new_size = current_size + add_size
    
    # 以读写模式打开文件
    with open(file_path, 'r+b') as f:
        # 获取文件描述符
        fd = f.fileno()
        
        # 使用 posix_fallocate 扩展文件
        # 这个函数会分配磁盘空间但不初始化数据（稀疏文件）
        try:
            os.posix_fallocate(fd, 0, new_size)
        except AttributeError:
            # 如果 posix_fallocate 不可用，回退到传统方法
            f.seek(new_size - 1)
            f.write(b'\0')
            f.flush()
def adjust_file_size_windows(file_path, add_size):
    """
    调整文件大小（Windows版本）
    
    参数:
        file_path: 文件路径
        new_size: 新的文件大小（字节）
    """
    global kernel32
    
    # 以读写模式打开文件
    with open(file_path, 'r+b') as f:
        # 获取文件描述符和 Windows 文件句柄
        fd = f.fileno()
        file_handle = msvcrt.get_osfhandle(fd)
        
        # 获取当前文件大小
        current_size = os.path.getsize(file_path)
        new_size = current_size+add_size
        
        # 设置文件指针到新的大小位置
        distance_to_move = LARGE_INTEGER(new_size)
        new_pointer = LARGE_INTEGER()
        
        success = kernel32.SetFilePointerEx(
            HANDLE(file_handle), 
            distance_to_move, 
            ctypes.byref(new_pointer), 
            0  # FILE_BEGIN
        )
        
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())
        
        # 设置文件结束位置
        success = kernel32.SetEndOfFile(HANDLE(file_handle))
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())
        
        # 尝试使用 SetFileValidData 优化（需要管理员权限）
        size_val = LARGE_INTEGER(new_size)
        success = kernel32.SetFileValidData(HANDLE(file_handle), size_val)
            

# 添加单位转换函数
def convert_to_bytes(size_str):
    units = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
    if size_str[-1].upper() in units:
        return int(float(size_str[:-1]) * units[size_str[-1].upper()])
    return int(size_str)

def fastwrite_on_windows(file_path, size):
    global kernel32

    # 首先以写入模式打开文件
    with open(file_path, 'wb') as f:
        # 获取文件描述符和 Windows 文件句柄
        fd = f.fileno()
        file_handle = msvcrt.get_osfhandle(fd)
        
        # 将文件扩展至指定大小
        f.seek(size - 1)
        f.write(b'\0')
        f.flush()
        
        # 使用 SetFileValidData 标记数据区域为有效
        # 这可以避免系统对文件内容进行零填充，提高大文件创建速度
        size_val = LARGE_INTEGER(size)
        success = kernel32.SetFileValidData(HANDLE(file_handle), size_val)
        
        if not success:
            # 如果 SetFileValidData 失败，回退到常规方法
            # 注意: SetFileValidData 需要管理员权限才能工作
            f.truncate(size)

def fastwrite_on_linux(file_path,size):
        # 首先，以写入模式打开文件
    with open(file_path, 'wb') as f:
        # 调用 posix_fallocate。
        # 这个函数会扩展文件到指定大小
        fd = f.fileno() # 获取文件描述符
        os.posix_fallocate(fd, 0, size) # 从偏移量0开始，扩展到size大小

def walk_path(path,is_append=False):
        print("扫描中……")
        if not is_append:
            walk = []
            for dir_path,_,_ in os.walk(path):
                if os.access(dir_path, os.W_OK):    #检查权限
                    walk.append(dir_path)    #有权限则添加
        else:
            walk = []
            for dir_path,_,files in os.walk(path):
                for file_name in files:
                    file_path = dir_path + os.sep + file_name
                    if os.access(file_path, os.W_OK):    #检查权限
                        walk.append(file_path)    #有权限则添加
        walk_len = len(walk)
        if walk_len == 0:
            print("将不会进行操作，需操作的文件为0")
            return walk
        print(f"需要操作的文件数量：{walk_len}")
        return walk



def run(path,type,size,write_func,is_hide=False):
    global os_type
    print(f"Write Size:{size}")
    if type == 'append' or type == 'a':   #追加模式
        step_size = size // 2 
        walk = walk_path(path,is_append=True)
        pbar = tqdm.tqdm(walk,unit='file')
        walk_len = len(walk)
        for filepath in pbar:   #遍历walk
            try:
                pbar.set_description(f"正在处理：{filepath}")
                if walk_len != 1:
                    write_func(filepath,step_size)  #写入   
                else:
                    write_func(filepath,size)
                if is_hide:
                    hide_file(os_type,filepath)
            except Exception as e:
                tqdm.write(f"出错：{filepath}:   {e}")
                walk_len -= 1
                continue
            size = size - step_size
            walk_len -= 1
            step_size = size // 2 
    elif type == 'splinters' or type == 's':     #碎片模式
        step_size = size // 2 
        walk = walk_path(path)
        pbar = tqdm.tqdm(walk,unit='file')
        walk_len = len(walk)
        for dirpath in pbar:    #遍历walk
            try:
                file_name = f'f{random.random()}.dat'
                filepath = dirpath + os.sep + file_name
                pbar.set_description(f"正在处理：{file_name}")
                if walk_len != 1:
                    write_func(filepath,step_size)  #写入   
                else:
                    write_func(filepath,size)
                if is_hide:
                    hide_file(os_type,filepath)
            except Exception as e:
                tqdm.write(f"出错：{filepath}:   {e}")
                walk_len -= 1
                continue
            size = size - step_size
            walk_len -= 1
            step_size = size // 2 
    elif type == 'onefile' or type == 'o':
        filepath = path + os.sep + f'f{random.random()}.dat'
        write_func(filepath,size)    #写入
        if is_hide:
            hide_file(os_type,filepath)
    else:
        print(f"格式错误{type}")
    print('Done')


if __name__ == '__main__':
    w_funcs = {
            "Windows":{False:fastwrite_on_windows,
                       True:adjust_file_size_windows
                       },
            "Linux":{False:fastwrite_on_linux,
                     True:extend_file_size_linux} 
            }
    os_type = platform.system()
    parse = argparse.ArgumentParser(description="~~~一个快速且高效的磁盘清理(填盘)的工具程序~~~\n注意：请以管理员身份运行")

    parse.add_argument('--path','-p',help="需要填满的磁盘（分区）的路径，如 'C:\\' , 'D:\\' 或者'/', '/home' ,默认为/程序工作目录/test",default='./test',type=str)
    parse.add_argument('--size',help="填充的大小，默认为10MB(请使用--size full 或者 --size [填充的大小] （支持K/M/G/T单位），如 10G)",type=str,default='10M')
    parse.add_argument('--mode','-m',help="模式,有追加（append,a）,单文件（onefile,o）,碎片模式（splinters,s）",type=str,default='onefile')
    parse.add_argument('--hide',help="是否隐藏文件（True,False）,如果使用该选项，请以管理员运行！！！",default=False,type=bool)

    args = parse.parse_args()
    try:
        use_disk = psutil.disk_usage(args.path)
    except FileNotFoundError:
        os.mkdir(path=args.path)
        use_disk = psutil.disk_usage(args.path)
    if args.size == 'full':
        size = use_disk.free
    else:
        set_size = convert_to_bytes(args.size)
        if  set_size <= use_disk.free:
            size = set_size
        else:
            size = use_disk.free - 1024 * 1024  
            print(f"设置的空间超出最大空间，已向下设置到{use_disk.free}")
    if args.hide == True:
        if not is_admin(os_type):
            print("无法隐藏，没有权限，程序已退出")
            exit(1)
        elif args.mode in ['a','append']:
            print("警告：你在追加模式下隐藏文件")
            i = input("是否继续(Y/N):")
            if i not in ["Y","y"]:
                print("程序已退出")
                sys.exit()
    

    is_append = args.mode in ('append', 'a')
        
    if os_type == 'Windows':
        import msvcrt
        # 定义必要的 Windows API 函数和常量
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        
        # 定义函数原型
        kernel32.SetFilePointerEx.argtypes = [HANDLE, LARGE_INTEGER, ctypes.POINTER(LARGE_INTEGER), DWORD]
        kernel32.SetFilePointerEx.restype = BOOL
        
        kernel32.SetEndOfFile.argtypes = [HANDLE]
        kernel32.SetEndOfFile.restype = BOOL
        
        kernel32.SetFileValidData.argtypes = [HANDLE, LARGE_INTEGER]
        kernel32.SetFileValidData.restype = BOOL
        run(args.path,args.mode,size,write_func=w_funcs[os_type][is_append],is_hide=args.hide)
    elif os_type == 'Linux':
        run(args.path,args.mode,size,write_func=w_funcs[os_type][is_append],is_hide=args.hide)
