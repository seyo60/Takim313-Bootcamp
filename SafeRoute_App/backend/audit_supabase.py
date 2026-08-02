import os
import asyncio
from urllib.parse import urlparse

async def run_audit():
    # Güvenlik gereksinimi: DATABASE_URL yalnızca os.environ üzerinden okunur.
    # Komut satırı argümanlarından kesinlikle okunmaz (OS process listesinde parola görünmemesi için).
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        print("[HATA] DATABASE_URL çevre değişkeni (os.environ['DATABASE_URL']) bulunamadı.")
        print("Lütfen PowerShell oturumunuzda $env:DATABASE_URL değişkeninin tanımlı olduğundan emin olun.")
        return

    # Güvenlik: Bağlantı dizesinden parola ve hassas bilgileri kesinlikle loglama
    try:
        clean_target = db_url.replace("postgresql+asyncpg://", "http://").replace("postgresql://", "http://")
        parsed = urlparse(clean_target)
        masked_host = f"{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}"
        print(f"[BİLGİ] Supabase hedef veritabanına salt-okunur bağlanılıyor (Host: {masked_host})")
    except Exception:
        print("[BİLGİ] Supabase hedef veritabanına salt-okunur bağlanılıyor...")

    conn = None
    try:
        import asyncpg
        clean_url = db_url.replace("postgresql+asyncpg://", "postgres://").replace("postgresql://", "postgres://")
        conn = await asyncpg.connect(clean_url)
    except Exception as e_asyncpg:
        try:
            import psycopg2
            clean_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
            conn_pg = psycopg2.connect(clean_url)

            class AsyncAdapter:
                def __init__(self, conn):
                    self.conn = conn
                async def fetch(self, query, *args):
                    with self.conn.cursor() as cur:
                        cur.execute(query, args)
                        colnames = [desc[0] for desc in cur.description] if cur.description else []
                        rows = cur.fetchall()
                        return [dict(zip(colnames, row)) for row in rows]
                async def fetchrow(self, query, *args):
                    rows = await self.fetch(query, *args)
                    return rows[0] if rows else None
                async def close(self):
                    self.conn.close()
            conn = AsyncAdapter(conn_pg)
        except Exception as e_pg:
            print(f"[HATA] Veritabanı bağlantısı kurulamadı: {e_asyncpg} | {e_pg}")
            return

    print("\n=======================================================")
    print("        SUPABASE HEDEF SALT-OKUNUR DENETİM RAPORU      ")
    print("=======================================================\n")

    # 1. Sayısal Satır Sayıları
    print("--- 1. TABLO SATIR SAYILARI ---")
    h3_cnt = await conn.fetchrow("SELECT COUNT(*) as count FROM h3_heatmap;")
    h3_count = h3_cnt['count'] if h3_cnt else 0
    print(f"h3_heatmap satır sayısı: {h3_count}")

    rep_cnt = await conn.fetchrow("SELECT COUNT(*) as count FROM reports;")
    reports_count = rep_cnt['count'] if rep_cnt else 0
    print(f"reports satır sayısı: {reports_count}")

    # 2. H3 Duplicate Kontrolü
    print("\n--- 2. H3 DUPLICATE KONTROLÜ ---")
    dup_rows = await conn.fetch("""
        SELECT h3_index, COUNT(*) as cnt
        FROM h3_heatmap
        GROUP BY h3_index
        HAVING COUNT(*) > 1;
    """)
    dup_group_count = len(dup_rows)
    total_dup_rows = sum([r['cnt'] for r in dup_rows]) if dup_rows else 0
    print(f"Duplicate Hücre Grubu Sayısı (HAVING COUNT > 1): {dup_group_count}")
    print(f"Toplam Duplicate Satır Sayısı: {total_dup_rows}")

    # 3. Risk Kolonları Değer Dağılımı (Kanonik ve Legacy)
    print("\n--- 3. KANONİK RİSK KOLONLARI DEĞER DAĞILIMI ---")
    h3_cols_fetch = await conn.fetch("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'h3_heatmap';
    """)
    existing_h3_cols = [r['column_name'] for r in h3_cols_fetch]

    canonical_cols = ['risk_crime', 'risk_lighting', 'risk_live', 'total_risk']
    for col in canonical_cols:
        if col in existing_h3_cols:
            q = f"""
                SELECT 
                    COUNT({col}) as count,
                    COUNT(*) FILTER (WHERE {col} IS NULL) as null_count,
                    MIN({col}) as min,
                    AVG({col}) as avg,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY {col}) as p50,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY {col}) as p95,
                    MAX({col}) as max,
                    COUNT(*) FILTER (WHERE {col} < 0.0 OR {col} > 1.0) as out_of_bounds_count
                FROM h3_heatmap;
            """
            dist = dict(await conn.fetchrow(q))
            avg_val = round(dist['avg'], 4) if dist['avg'] is not None else None
            print(f"  [{col}] COUNT={dist['count']}, NULL={dist['null_count']}, MIN={dist['min']}, AVG={avg_val}, P50={dist['p50']}, P95={dist['p95']}, MAX={dist['max']}, OutOfBounds={dist['out_of_bounds_count']}")
        else:
            print(f"  [{col}] KOLON TABLODA MEVCUT DEĞİL")

    print("\n--- 4. KALDIRILMASI GEREKEN LEGACY RİSK KOLONLARI ---")
    legacy_cols = ['risk_historical', 'risk_social']
    for col in legacy_cols:
        if col in existing_h3_cols:
            print(f"  [HATA] {col} hâlâ mevcut")
        else:
            print(f"  [OK] {col} mevcut değil")

    # 5. Location NULL Sayıları
    print("\n--- 5. LOCATION NULL SAYILARI ---")
    if 'location' in existing_h3_cols:
        h3_loc_null = await conn.fetchrow("SELECT COUNT(*) FILTER (WHERE location IS NULL) as null_count FROM h3_heatmap;")
        print(f"h3_heatmap.location NULL sayısı: {h3_loc_null['null_count']}")
    else:
        print("h3_heatmap.location kolonu mevcut değil")

    rep_cols_fetch = await conn.fetch("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'reports';
    """)
    existing_rep_cols = [r['column_name'] for r in rep_cols_fetch]
    if 'location' in existing_rep_cols:
        rep_loc_null = await conn.fetchrow("SELECT COUNT(*) FILTER (WHERE location IS NULL) as null_count FROM reports;")
        print(f"reports.location NULL sayısı: {rep_loc_null['null_count']}")
    else:
        print("reports.location kolonu mevcut değil")

    # 6. ETL Runs Durumu
    print("\n--- 6. ETL RUNS TABLOSU DURUMU ---")
    etl_tables = await conn.fetch("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'etl_runs';
    """)
    if etl_tables:
        etl_rows = await conn.fetch("SELECT etl_name, last_successful_run, records_processed, status FROM etl_runs ORDER BY etl_name;")
        if etl_rows:
            for r in etl_rows:
                print(f"  [{r['etl_name']}] Status={r['status']}, İşlenen Kayıt={r['records_processed']}, Son Başarı Tarihi={r['last_successful_run']}")
        else:
            print("  etl_runs tablosu mevcut ancak kayıt yok.")
    else:
        print("  etl_runs tablosu veritabanında bulunamadı.")

    await conn.close()
    print("\n=======================================================")
    print("                DENETİM TAMAMLANDI                     ")
    print("=======================================================\n")

if __name__ == "__main__":
    asyncio.run(run_audit())
