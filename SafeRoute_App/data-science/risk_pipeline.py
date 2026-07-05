import h3
import osmnx as ox
from shapely.geometry import Polygon

class RouteRiskPipeline:
    def __init__(self, resolution=9):
        # Sınıf başlatıldığında H3 çözünürlüğünü varsayılan olarak 9 ayarlıyoruz.
        self.resolution = resolution

    def get_h3_index(self, lat, lon):
        """Koordinatları H3 altıgen ID'sine çevirir."""
        try:
            return h3.latlng_to_cell(lat, lon, self.resolution)
        except Exception as e:
            print(f"H3 Dönüşüm Hatası: {e}")
            return None

    def apply_dynamic_risk(self, lat, lon, ai_risk_score):
        """
        Canlı ihbar koordinatlarını alır, altıgeni bulur, sokak ağını çeker
        ve yapay zekadan gelen risk skorunu sokaklara işler.
        """
        # 1. Altıgen ID'sini bul
        hex_id = self.get_h3_index(lat, lon)
        if not hex_id:
            return None

        # 2. Altıgen sınırlarını poligon yap
        boundaries = h3.cell_to_boundary(hex_id)
        hex_polygon = Polygon([(lon, lat) for lat, lon in boundaries])

        try:
            # 3. Sokak ağını indir
            G = ox.graph_from_polygon(hex_polygon, network_type='drive')

            # 4. Ağırlıkları işle
            processed_edges = 0
            for u, v, key, data in G.edges(keys=True, data=True):
                data['anlik_risk'] = ai_risk_score
                processed_edges += 1

            return {
                "status": "success",
                "hex_id": hex_id,
                "processed_streets_count": processed_edges,
                "graph_data": G  # Bu graf objesi daha sonra rotalama için kullanılacak
            }

        except Exception as e:
            print(f"OSMnx İşlem Hatası: {e}")
            return {"status": "error", "message": str(e)}

    def export_graph_to_csv(self, G, filename="chicago_clean_data.csv"):
        """
        Graf verisindeki sokakları, geometrileri ve anlık risk skorlarını
        backend ekibinin API üzerinden rahatça okuyabileceği CSV formatına dönüştürür.
        """
        try:
            # 1. Graf objesini GeoDataFrame'e çeviriyoruz (Sadece sokak segmentlerini/edges alıyoruz)
            edges = ox.graph_to_gdfs(G, nodes=False, edges=True)

            # 2. Backend için en kritik sütunları seçiyoruz
            columns_to_keep = ['osmid', 'name', 'anlik_risk', 'geometry']

            # Sokağın adı yoksa hata almamak için sadece var olan sütunları filtreliyoruz
            available_columns = [col for col in columns_to_keep if col in edges.columns]
            clean_data = edges[available_columns].copy()

            # 3. Harita çizgilerini (MULTILINESTRING) CSV'de düzgün durması için metne (WKT) çeviriyoruz
            if 'geometry' in clean_data.columns:
                clean_data['geometry'] = clean_data['geometry'].apply(lambda x: x.wkt)

            # 4. Temiz veriyi CSV olarak kaydediyoruz
            clean_data.to_csv(filename, index=False)
            print(f"Veri başarıyla {filename} olarak dışa aktarıldı!")

            return True

        except Exception as e:
            print(f"CSV Dışa Aktarma Hatası: {e}")
            return False


# --- SİSTEM TESTİ VE ÇALIŞTIRMA (Burası sınıfın dışında, en solda olmalı) ---
if __name__ == "__main__":
    print("Pipeline başlatılıyor...")
    # 1. Pipeline'ı başlat
    pipeline = RouteRiskPipeline()

    # 2. Canlı veriyi işle (Örnek Koordinat ve Risk Puanı)
    sonuc = pipeline.apply_dynamic_risk(lat=41.8781, lon=-87.6298, ai_risk_score=9.8)

    # 3. İşlem başarılıysa veriyi CSV'ye dök
    if sonuc and sonuc["status"] == "success":
        print(f"Altıgen ({sonuc['hex_id']}) içindeki {sonuc['processed_streets_count']} sokağa risk atandı.")
        pipeline.export_graph_to_csv(sonuc["graph_data"])