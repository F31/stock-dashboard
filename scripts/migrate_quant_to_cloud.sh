#!/bin/bash
# 量化数据迁移 — 把本地 stock_dashboard.db 的量化表同步到云主机
# 保留云主机用户账号数据
set -e

CLOUD_HOST="101.133.238.118"
LOCAL_DB="/root/projects/stock-dashboard/backend/data/stock_dashboard.db"
REMOTE_DB="/root/projects/stock-dashboard/backend/data/stock_dashboard.db"
TEMP_DUMP="/tmp/quant_migrate_$(date +%Y%m%d).sql"

# ── 表分类 ──
QUANT_TABLES="quan_daily_scores quan_stock_info quan_tech_levels quan_sentiment_daily"

echo "=== 1. 从本地导出量化表 ==="
python3 << PYEOF
import sqlite3
src = sqlite3.connect("$LOCAL_DB")
with open("$TEMP_DUMP", "w", encoding="utf-8") as f:
    for table in "$QUANT_TABLES".split():
        cnt = src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"    {table}: {cnt:,} 行")
        cols = [c[1] for c in src.execute(f"PRAGMA table_info({table})")]
        names = ",".join(f'"{c}"' for c in cols)
        f.write(f"DELETE FROM {table};\n")
        for row in src.execute(f"SELECT {names} FROM {table}"):
            vals = []
            for v in row:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    escaped = str(v).replace("'", "''")
                    vals.append(f"'{escaped}'")
            f.write(f"INSERT INTO {table} ({names}) VALUES ({','.join(vals)});\n")
import os
print(f"  导出文件: {os.path.getsize('$TEMP_DUMP')//1024} KB")
PYEOF

echo ""
echo "=== 2. 上传到云主机 ==="
scp "$TEMP_DUMP" "root@${CLOUD_HOST}:/tmp/"

echo ""
echo "=== 3. 云主机导入（先备份） ==="
ssh "root@${CLOUD_HOST}" bash << REMOTE
set -e
DB="$REMOTE_DB"
DUMP="/tmp/$(basename $TEMP_DUMP)"

cp "\$DB" "\${DB}.backup_\$(date +%Y%m%d_%H%M%S)"
echo "  已备份云主机数据库"

sqlite3 "\$DB" < "\$DUMP"
echo "  导入完成:"

for t in $QUANT_TABLES; do
    cnt=\$(sqlite3 "\$DB" "SELECT COUNT(*) FROM \$t" 2>/dev/null || echo 0)
    echo "    \$t: \$cnt 行"
done
rm -f "\$DUMP"
REMOTE

echo ""
echo "=== 4. 重启后端 ==="
ssh "root@${CLOUD_HOST}" "systemctl restart stock-dashboard 2>/dev/null || pkill -HUP -f 'uvicorn main:app' 2>/dev/null || echo '请手动重启'"

echo ""
echo "✓ 完成"
