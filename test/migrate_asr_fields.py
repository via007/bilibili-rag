"""
数据库迁移脚本 - 添加 ASR 相关字段

使用方法:
    python test/migrate_asr_fields.py
"""
import sqlite3
import os

DB_PATH = "./data/bilibili_rag.db"

def migrate():
    """执行数据库迁移"""
    if not os.path.exists(DB_PATH):
        print(f"数据库文件不存在: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_cache'")
    if not cursor.fetchone():
        print("video_cache 表不存在")
        conn.close()
        return False

    # 需要添加的字段
    new_columns = [
        ("asr_model", "VARCHAR(50)"),
        ("asr_duration", "INTEGER"),
        ("asr_quality_score", "REAL"),
        ("asr_quality_flags", "TEXT"),  # JSON in SQLite
        ("is_corrected", "INTEGER DEFAULT 0"),
        ("corrected_content", "TEXT"),
        ("corrected_at", "TIMESTAMP"),
        ("corrected_by", "VARCHAR(50)"),
    ]

    # 检查并添加字段
    cursor.execute("PRAGMA table_info(video_cache)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE video_cache ADD COLUMN {col_name} {col_type}")
                print(f"添加字段成功: {col_name}")
            except Exception as e:
                print(f"添加字段失败 {col_name}: {e}")
        else:
            print(f"字段已存在: {col_name}")

    # 创建 asr_quality_logs 表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='asr_quality_logs'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE asr_quality_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bvid VARCHAR(20) NOT NULL,
                quality_score REAL NOT NULL,
                quality_flags TEXT,
                confidence_avg REAL,
                confidence_min REAL,
                audio_duration INTEGER,
                audio_quality VARCHAR(20),
                speech_ratio REAL,
                asr_model VARCHAR(50),
                word_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("创建表成功: asr_quality_logs")

        # 创建索引
        cursor.execute("CREATE INDEX ix_asr_quality_logs_bvid ON asr_quality_logs(bvid)")
        cursor.execute("CREATE INDEX ix_asr_quality_logs_bvid_created ON asr_quality_logs(bvid, created_at)")
        print("创建索引成功: asr_quality_logs")
    else:
        print("表已存在: asr_quality_logs")

    # 创建 correction_history 表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='correction_history'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE correction_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bvid VARCHAR(20) NOT NULL,
                original_content TEXT NOT NULL,
                corrected_content TEXT NOT NULL,
                char_diff INTEGER DEFAULT 0,
                word_diff INTEGER DEFAULT 0,
                correction_type VARCHAR(20) DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("创建表成功: correction_history")

        # 创建索引
        cursor.execute("CREATE INDEX ix_correction_history_bvid ON correction_history(bvid)")
        print("创建索引成功: correction_history")
    else:
        print("表已存在: correction_history")

    # 创建 chat_sessions 表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_sessions'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(64) NOT NULL,
                user_session_id VARCHAR(64) NOT NULL,
                title VARCHAR(200),
                folder_ids TEXT,
                message_count INTEGER DEFAULT 0,
                last_message_at TIMESTAMP,
                is_archived INTEGER DEFAULT 0,
                is_deleted INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("创建表成功: chat_sessions")

        # 创建索引
        cursor.execute("CREATE INDEX ix_chat_sessions_session_id ON chat_sessions(session_id)")
        cursor.execute("CREATE INDEX ix_chat_sessions_user_session_id ON chat_sessions(user_session_id)")
        cursor.execute("CREATE INDEX ix_chat_sessions_user_del_archived ON chat_sessions(user_session_id, is_deleted, is_archived)")
        print("创建索引成功: chat_sessions")
    else:
        print("表已存在: chat_sessions")

    # 创建 chat_messages 表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_session_id VARCHAR(64) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                sources TEXT,
                context_token_count INTEGER DEFAULT 0,
                route VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("创建表成功: chat_messages")

        # 创建索引
        cursor.execute("CREATE INDEX ix_chat_messages_session_id ON chat_messages(chat_session_id)")
        print("创建索引成功: chat_messages")
    else:
        print("表已存在: chat_messages")

    conn.commit()
    conn.close()
    print("\n数据库迁移完成!")
    return True


if __name__ == "__main__":
    migrate()
