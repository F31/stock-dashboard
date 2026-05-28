#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# 量化评分数据导出脚本 — 含子板块配置、产业链配置、行业数据补齐
#
# 用法:
#   bash export_quan_data.sh                          # 默认导出
#   bash export_quan_data.sh -o /tmp/quan_sync.sql    # 指定输出文件
#   bash export_quan_data.sh --scp user@host          # 导出 + scp 到云主机
#   bash export_quan_data.sh --no-fill                # 跳过行业补齐步骤
#   bash export_quan_data.sh --help                   # 查看帮助
#
# 新增（相比旧版）:
#   - system_settings      含 subsector_config（子板块配置，不再写死在代码中）
#   - analysis_framework   产业链实体配置（含 subsector 字段）
#   - northbound_holdings  北向资金数据
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJ="/root/projects/stock-dashboard"
QLIB="/root/projects/stock_quan"
DB="${PROJ}/backend/data/stock_dashboard.db"
SECTOR_CACHE="${QLIB}/data/sector_cache.db"
OUTPUT="/tmp/quan_sync.sql"
SCP_TARGET=""
SKIP_FILL=false

# ── 解析参数 ──
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output)   OUTPUT="$2"; shift 2 ;;
    --scp)         SCP_TARGET="$2"; shift 2 ;;
    --no-fill)     SKIP_FILL=true; shift ;;
    --help|-h)
      echo "用法: bash export_quan_data.sh [-o 文件] [--scp user@host] [--no-fill]"
      echo ""
      echo "  -o 文件       输出路径（默认 /tmp/quan_sync.sql）"
      echo "  --scp 目标    导出后自动 scp 到云主机"
      echo "  --no-fill     跳过导出前行业数据补齐"
      exit 0 ;;
    *) echo "❌ 未知参数: $1"; exit 1 ;;
  esac
done

# ── 检查数据库 ──
if [[ ! -f "$DB" ]]; then
  echo "❌ 数据库不存在: $DB"
  exit 1
fi

echo "========================================"
echo "  量化评分 + 配置数据导出"
echo "  数据库: $DB"
echo "  输出:   $OUTPUT"
echo "========================================"

# ── 第一步：补齐缺失的行业数据 ──
if [[ "$SKIP_FILL" = false && -f "$SECTOR_CACHE" ]]; then
  echo ""
  echo "▸ 检查并补齐缺失的行业数据 ..."

  MISSING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM quan_stock_info WHERE industry IS NULL OR industry = '';")
  if [[ "$MISSING" -gt 0 ]]; then
    echo "  发现 $MISSING 条记录缺少行业数据，从 EM2016 缓存补齐 ..."

    TMP_CODES=$(mktemp)
    sqlite3 "$DB" "SELECT stock_code FROM quan_stock_info WHERE industry IS NULL OR industry = '';" > "$TMP_CODES"

    UPDATED=0
    while IFS= read -r code; do
      [[ -z "$code" ]] && continue
      IND=$(sqlite3 "$SECTOR_CACHE" \
        "SELECT em2016 FROM em2016_cache WHERE stock_code='$code';" 2>/dev/null || true)
      if [[ -n "$IND" ]]; then
        sqlite3 "$DB" \
          "UPDATE quan_stock_info SET industry='$IND', updated_at=datetime('now') WHERE stock_code='$code';"
        UPDATED=$((UPDATED + 1))
      fi
    done < "$TMP_CODES"
    rm -f "$TMP_CODES"
    echo "  已补齐 $UPDATED 条"

    STILL_MISSING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM quan_stock_info WHERE industry IS NULL OR industry = '';")
    if [[ "$STILL_MISSING" -gt 0 ]]; then
      echo "  仍有 $STILL_MISSING 条不在缓存中，尝试从 EM API 获取 ..."
      cd "$QLIB"
      PYTHONPATH="$QLIB" python3 -c "
import sys, sqlite3
sys.path.insert(0, '$QLIB')
from core.stock_info import fetch_industries
db = sqlite3.connect('$DB')
codes = [r[0] for r in db.execute(
    \"SELECT stock_code FROM quan_stock_info WHERE industry IS NULL OR industry = ''\").fetchall()]
if codes:
    result = fetch_industries(codes)
    for code, ind in result.items():
        db.execute(\"UPDATE quan_stock_info SET industry=?, updated_at=datetime('now') WHERE stock_code=?\", (ind, code))
    db.commit()
    print(f'  从 EM API 获取了 {len(result)} 条')
db.close()
" 2>/dev/null || echo "  ⚠️  EM API 获取失败，跳过"
    fi
  else
    echo "  行业数据完整，无需补齐"
  fi
elif [[ "$SKIP_FILL" = false ]]; then
  echo "  ⚠️  EM2016 行业缓存不存在 ($SECTOR_CACHE)，跳过补齐"
fi

# ── 数据完整性检查 ──
echo ""
echo "▸ 数据完整性检查 ..."
EMPTY_IND=$(sqlite3 "$DB" "SELECT COUNT(*) FROM quan_stock_info WHERE industry IS NULL OR industry = '';")
TOTAL_INFO=$(sqlite3 "$DB" "SELECT COUNT(*) FROM quan_stock_info;")
TOTAL_SCORES=$(sqlite3 "$DB" "SELECT COUNT(*) FROM quan_daily_scores;")
echo "  quan_stock_info: $TOTAL_INFO 条（其中 $EMPTY_IND 条行业为空）"
echo "  quan_daily_scores: $TOTAL_SCORES 条"

# ── 需要导出的表 ──
# 量化数据 + 配置数据（含子板块配置、产业链配置）
TABLES=(
  # 量化评分数据
  "quan_daily_scores"
  "quan_stock_info"
  "quan_tech_levels"
  "quan_sentiment_daily"
  "daily_pe"
  "capex_quarterly"
  "earnings_quarterly"
  "earnings_guidance"
  # 配置数据（子板块配置不再写死在代码里，需同步）
  "system_settings"
  "analysis_framework"
  # 北向资金（可选依赖，如果表存在则导出）
)

# ── 导出每张表 ──
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

EXPORTED_TABLES=()
for table in "${TABLES[@]}"; do
  EXISTS=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='$table';" 2>/dev/null || true)
  if [[ -z "$EXISTS" ]]; then
    echo "  ⚠️  跳过: $table (表不存在)"
    continue
  fi

  ROWS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM $table;")
  echo "  📦 导出: $table ($ROWS 行) ..."

  # 跳过导出的场合: system_settings 中敏感配置
  if [[ "$table" == "system_settings" ]]; then
    # 只导出 subsector_config，不导出敏感配置
    sqlite3 "$DB" \
      ".mode insert system_settings" \
      ".output $TMPDIR/system_settings.sql" \
      "SELECT key, value FROM system_settings WHERE key IN ('subsector_config');" \
      ".output stdout" 2>/dev/null
    EXPORTED_TABLES+=("system_settings")
    echo "    (仅 subsector_config 键)"
    continue
  fi

  sqlite3 "$DB" \
    ".mode insert $table" \
    ".output $TMPDIR/$table.sql" \
    "SELECT * FROM $table;" \
    ".output stdout" 2>/dev/null

  EXPORTED_TABLES+=("$table")
done

# ── 合并并替换为 INSERT OR REPLACE ──
echo ""
echo "▸ 合并为 INSERT OR REPLACE ..."
> "$OUTPUT"
echo "PRAGMA foreign_keys=OFF;" >> "$OUTPUT"
echo "BEGIN TRANSACTION;" >> "$OUTPUT"

for table in "${EXPORTED_TABLES[@]}"; do
  if [[ -f "$TMPDIR/$table.sql" ]]; then
    sed 's/^INSERT INTO/INSERT OR REPLACE INTO/' "$TMPDIR/$table.sql" >> "$OUTPUT"
  fi
done

echo "COMMIT;" >> "$OUTPUT"

# ── 统计 ──
SIZE=$(wc -c < "$OUTPUT")
echo ""
echo "▸ 导出完成"
echo "  文件: $OUTPUT"
echo "  大小: $(numfmt --to=iec $SIZE 2>/dev/null || echo "$SIZE bytes")"
echo ""

echo "  包含的表:"
for table in "${EXPORTED_TABLES[@]}"; do
  CNT=$(grep -c "INSERT OR REPLACE INTO $table" "$OUTPUT" 2>/dev/null || echo 0)
  echo "    ✅ $table ($CNT 条)"
done

# ── 可选: scp 到云主机 ──
if [[ -n "$SCP_TARGET" ]]; then
  echo ""
  echo "▸ scp 到 $SCP_TARGET ..."
  scp "$OUTPUT" "${SCP_TARGET}:/tmp/quan_sync.sql"
  echo "  ✅ scp 完成"
fi

# ── 导入指引 ──
echo ""
echo "========================================"
echo "  📋 在云主机上执行导入命令:"
echo ""
echo "    sqlite3 /path/stock-dashboard/backend/data/stock_dashboard.db < $OUTPUT"
echo ""
echo "  🔍 验证:"
echo '    sqlite3 /path/db "SELECT model_name, trade_date, COUNT(*)'
echo '     FROM quan_daily_scores GROUP BY model_name, trade_date'
echo '     ORDER BY trade_date DESC LIMIT 5;"'
echo ""
echo "  🔍 子板块配置验证:"
echo '    sqlite3 /path/db "SELECT value FROM system_settings'
echo "     WHERE key='subsector_config';\" | head -c 200"
echo ""
echo "  📋 云主机首次部署额外步骤:"
echo "    1. rsync 或 git pull 同步整个 stock_quan 和 stock-dashboard 项目"
echo "    2. 运行: cd /root/projects/stock_quan"
echo "       /root/qlib/qvenv/bin/python scripts/init_subsector_config.py --push"
echo "       （确保子板块配置写入DB，仅首次部署需要）"
echo "========================================"
