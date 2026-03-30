#!/usr/bin/env python
# -*- coding: utf-8 -*-

print("=" * 60)
print("模組導入診斷測試")
print("=" * 60)

# 測試 1: Motor_global_vars
print("\n【測試 1】Motor_global_vars 導入...")
try:
    from modules import Motor_global_vars
    print("✓ Motor_global_vars 導入成功")
    print(f"  - Motor_P: {Motor_global_vars.Motor_P}")
except Exception as e:
    print(f"✗ Motor_global_vars 失敗: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# 測試 2: command_485
print("\n【測試 2】command_485 導入...")
try:
    from modules import command_485
    print("✓ command_485 導入成功")
except Exception as e:
    print(f"✗ command_485 失敗: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# 測試 3: Data_handle
print("\n【測試 3】Data_handle 導入...")
try:
    from modules import Data_handle
    print("✓ Data_handle 導入成功")
except Exception as e:
    print(f"✗ Data_handle 失敗: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# 測試 4: Data_handle_in_IPC
print("\n【測試 4】Data_handle_in_IPC 導入...")
try:
    from modules import Data_handle_in_IPC
    print("✓ Data_handle_in_IPC 導入成功")
except Exception as e:
    print(f"✗ Data_handle_in_IPC 失敗: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("診斷完成")
print("=" * 60)
