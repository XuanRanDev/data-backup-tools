你是资深 Python 桌面软件工程师，请为 Windows 10/11 开发一个“离线备份助手”GUI，主要用于把手机/相机/屏幕录制等数据整理到外接 SATA HDD，并对部分内容做 7z 加密（支持加密文件名）。我希望使用 Python 实现，优先选 PySide6（或 PyQt6），代码要结构清晰、可扩展、便于我后续加功能。

【核心目标】
1) 备份目录结构固定为：
   <目标盘根目录>\BACKUP\<YYYY>\<MM>\<SourceType>\
   例如：BACKUP\2025\10\Camera\
        BACKUP\2025\10\ScreenRecorder\
   并且在每个月目录下有一个 ENCRYPTED 文件夹（注意：名字是 ENCRYPTED，不是 _ENCRYPTED）：
        BACKUP\2025\10\ENCRYPTED\
   ENCRYPTED 里“直接放加密后的 .7z 文件”，而不是再套一层子目录。

2) 用户不是每次备份都按月进行，可能一次导入跨好几个月：
   - 程序需要支持“按文件的拍摄/创建时间自动分配到 YYYY/MM”
   - 允许用户选择使用「文件的修改时间」或「EXIF(如果可用)」或「文件创建时间」作为归类依据（默认修改时间）

3) 加密是可选的：
   - 用户可选择某一批文件“明文复制”到对应的 SourceType 文件夹
   - 或选择“加密归档”到对应月份的 ENCRYPTED 里（生成一个 .7z）
   - 加密归档必须支持 7-Zip 参数：-mhe=on（加密文件名）+ AES-256 + -mx=9
   - 提供可选开关：是否加入恢复记录 -rr5%（默认开启）

4) 校验（可选但推荐默认开）：
   - 对每个生成的 .7z 文件计算 SHA256，并生成同名 .sha256 文件放在同一目录（ENCRYPTED 内）
   - 程序提供“验证校验”按钮：重新计算 hash 并与 .sha256 比较，显示通过/失败

5) 备份日志：
   - 在 <目标盘>\BACKUP\_INDEX\BACKUP_LOG.csv 记录每一次操作
   - 字段至少包括：timestamp, job_id, source_path, target_drive, yyyy, mm, source_type, mode(plain/encrypted), archive_name, size_bytes, sha256, notes
   - 若目录不存在则自动创建

【GUI 需求】
- 窗口分区建议：
  A. 源选择：可多选文件夹/文件（拖拽支持）
  B. 目标盘选择：下拉列出当前可用盘符（可刷新）
  C. SourceType 下拉：Camera / ScreenRecorder / Phone / Download / Other（可编辑）
  D. 归类规则：按修改时间/创建时间/EXIF（单选）
  E. 模式选择：明文复制 / 加密归档（单选）
  F. 加密设置区（仅加密模式显示）：密码输入框（可显示/隐藏），rr% 开关
  G. 运行按钮：预览（显示将要写入的 YYYY/MM 统计）、开始执行、查看日志、校验验证

【实现细节】
- 需要检查目标盘是否存在 BACKUP 目录，没有则创建
- 对明文复制：建议保持原文件名，避免覆盖时自动加后缀（(1)、(2)）或提示冲突策略
- 对加密归档：
  - 每个 YYYY/MM 生成一个归档（更易管理）；归档命名建议：
    YYYY-MM__<SourceType>__<JobID>.7z
  - 归档内部保留原始相对路径（例如按日期或原目录结构），但外部放在 ENCRYPTED 直接是文件
  - 调用系统已安装的 7z.exe（优先检测常见路径，如 "C:\Program Files\7-Zip\7z.exe"；若未找到提示用户选择）
- 大文件复制要显示进度条和剩余时间估计（可粗略）
- 处理错误：磁盘空间不足、文件被占用、7z 执行失败、hash 计算失败等

【交付内容】
- 给出完整可运行的项目代码（一个入口 main.py）
- 清楚列出依赖安装命令（pip install ...）
- 给出简单使用说明
- 代码里把“目录结构规则、文件命名规则、日志字段”封装成配置常量，便于我修改

请直接输出代码，不要省略关键实现。
