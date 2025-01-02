
import tkinter as tk
from tkinter import ttk
import serial.tools.list_ports

# root = tk.Tk()
# root.title("選擇 COM 埠")

def select_com_port():

    # create window
    root = tk.Tk()
    root.title("選擇 COM 埠")

    # label
    label = ttk.Label(root, text="請選擇 COM 埠號:")
    label.pack(pady=10)

    # get comport list
    def get_com_ports():
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def close_window():
        root.destroy()  # 关闭窗口

    # scroll bar variable
    com_var = tk.StringVar()

    # visualize scroll bar
    com_ports = get_com_ports()
    com_dropdown = ttk.Combobox(root, textvariable=com_var)
    com_dropdown['values'] = com_ports  # list available COM
    com_dropdown.pack(pady=10)

    # implement selection
    def on_select():
        selected_port = com_var.get()
        if selected_port:  # if selected
            root.selected_port = selected_port
        root.quit()  # end window

    submit_button = ttk.Button(root, text="確認", command=on_select)
    submit_button.pack(pady=10)

    # hold the window
    root.mainloop()

    button = tk.Button(root, text="Close", command=close_window)

    # return the select comport
    return getattr(root, 'selected_port', None)

def select_comport():
    """
    弹出一个窗口供用户选择 COM 端口，返回所选端口的字符串值。
    如果未选择或无可用端口，则返回 None。
    """
    def on_confirm():
        """确认按钮回调函数"""
        nonlocal selected_port
        selected_port = port_combobox.get()
        root.destroy()  # 关闭窗口

    def get_available_ports():
        """获取所有可用的 COM 端口列表"""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    # 初始化返回值
    selected_port = None

    # 创建主窗口
    root = tk.Tk()
    root.title("COM Port Selector")
    root.geometry("300x150")

    # 标签
    label = tk.Label(root, text="Select a COM port:")
    label.pack(pady=10)

    # 获取可用的 COM 端口
    com_ports = get_available_ports()

    # 下拉菜单 (Combobox)
    port_combobox = ttk.Combobox(root, values=com_ports, state="readonly")
    port_combobox.pack(pady=5)

    # 设置默认值（如果有可用端口）
    if com_ports:
        port_combobox.current(0)  # 默认选择第一个端口

    # 确认按钮
    confirm_button = tk.Button(root, text="Confirm", command=on_confirm)
    confirm_button.pack(pady=10)

    # 运行主循环
    root.mainloop()

    # 返回结果
    return selected_port
