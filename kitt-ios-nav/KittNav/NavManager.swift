import Foundation
import MapKit
import Combine

/// Firebase RTDBを監視してナビ先を自動更新
///
/// /nav パスの変更を検知:
///   { destination: {lat, lng, name}, type: "pick"|"drop"|"standby", timestamp }
///
/// 変更検知 → MKDirectionsでルート計算 → 地図にルート表示 + ETA更新
class NavManager: NSObject, ObservableObject, CLLocationManagerDelegate {

    @Published var destination: Destination?
    @Published var navType: String = ""
    @Published var route: MKRoute?
    @Published var eta: String?
    @Published var cameraPosition: MapCameraPosition = .userLocation(fallback: .automatic)

    private let locationManager = CLLocationManager()
    private var pollingTimer: Timer?
    private var lastTimestamp: Int64 = 0

    private let rtdbURL = "https://ubereats-kitt-default-rtdb.asia-southeast1.firebasedatabase.app"

    struct Destination {
        let coordinate: CLLocationCoordinate2D
        let name: String
    }

    override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracy.best
        locationManager.requestAlwaysAuthorization()
        locationManager.startUpdatingLocation()
    }

    /// Firebase RTDBポーリング開始 (3秒間隔)
    func startListening() {
        pollingTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
            self?.checkForNavUpdate()
        }
    }

    private func checkForNavUpdate() {
        guard let url = URL(string: "\(rtdbURL)/nav.json") else { return }

        URLSession.shared.dataTask(with: url) { [weak self] data, _, error in
            guard let self = self, let data = data, error == nil else { return }

            do {
                guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    // navがnull = ナビなし
                    DispatchQueue.main.async {
                        self.destination = nil
                        self.route = nil
                        self.eta = nil
                        self.navType = ""
                    }
                    return
                }

                let timestamp = json["timestamp"] as? Int64 ?? 0

                // 同じタイムスタンプならスキップ
                if timestamp == self.lastTimestamp { return }
                self.lastTimestamp = timestamp

                let type = json["type"] as? String ?? ""

                guard let dest = json["destination"] as? [String: Any],
                      let lat = dest["lat"] as? Double,
                      let lng = dest["lng"] as? Double,
                      let name = dest["name"] as? String else { return }

                DispatchQueue.main.async {
                    self.navType = type
                    self.destination = Destination(
                        coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lng),
                        name: name
                    )
                    self.calculateRoute(to: CLLocationCoordinate2D(latitude: lat, longitude: lng))
                }

            } catch {
                print("Nav parse error: \(error)")
            }
        }.resume()
    }

    /// ルート計算 + ETA更新
    private func calculateRoute(to coordinate: CLLocationCoordinate2D) {
        guard let userLocation = locationManager.location?.coordinate else { return }

        let request = MKDirections.Request()
        request.source = MKMapItem(placemark: MKPlacemark(coordinate: userLocation))
        request.destination = MKMapItem(placemark: MKPlacemark(coordinate: coordinate))
        request.transportType = .automobile

        let directions = MKDirections(request: request)
        directions.calculate { [weak self] response, error in
            guard let self = self, let route = response?.routes.first else {
                print("Route calculation failed: \(error?.localizedDescription ?? "unknown")")
                return
            }

            DispatchQueue.main.async {
                self.route = route

                // ETA計算
                let minutes = Int(route.expectedTravelTime / 60)
                self.eta = "\(minutes)分"

                // カメラをルートに合わせる
                let rect = route.polyline.boundingMapRect
                self.cameraPosition = .rect(rect.insetBy(dx: -rect.width * 0.2, dy: -rect.height * 0.2))
            }
        }
    }

    // MARK: - CLLocationManagerDelegate

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        // 位置更新は自動的にMapのUserAnnotationに反映される
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if manager.authorizationStatus == .authorizedAlways ||
           manager.authorizationStatus == .authorizedWhenInUse {
            manager.startUpdatingLocation()
        }
    }
}
