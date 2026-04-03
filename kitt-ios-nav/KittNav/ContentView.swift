import SwiftUI
import MapKit

struct ContentView: View {
    @EnvironmentObject var navManager: NavManager

    var body: some View {
        ZStack {
            // 地図 (ナビ表示)
            Map(position: $navManager.cameraPosition) {
                // 現在地
                UserAnnotation()

                // 目的地マーカー
                if let dest = navManager.destination {
                    Marker(dest.name, coordinate: dest.coordinate)
                        .tint(markerColor)
                }

                // ルート表示
                if let route = navManager.route {
                    MapPolyline(route.polyline)
                        .stroke(.blue, lineWidth: 5)
                }
            }
            .mapStyle(.standard(elevation: .flat))
            .mapControls {
                MapUserLocationButton()
                MapCompass()
            }

            // 上部: ナビ情報バー
            VStack {
                if let dest = navManager.destination {
                    HStack {
                        // ナビタイプアイコン
                        Image(systemName: navTypeIcon)
                            .foregroundColor(markerColor)
                            .font(.title2)

                        VStack(alignment: .leading) {
                            Text(navTypeLabel)
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text(dest.name)
                                .font(.headline)
                                .foregroundColor(.primary)
                        }

                        Spacer()

                        // 到着予想
                        if let eta = navManager.eta {
                            VStack(alignment: .trailing) {
                                Text("到着")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text(eta)
                                    .font(.title2)
                                    .fontWeight(.bold)
                                    .foregroundColor(.primary)
                            }
                        }
                    }
                    .padding()
                    .background(.ultraThinMaterial)
                    .cornerRadius(12)
                    .padding(.horizontal)
                } else {
                    // 待機中
                    Text("KITT Nav - 待機中")
                        .font(.headline)
                        .foregroundColor(.secondary)
                        .padding()
                        .background(.ultraThinMaterial)
                        .cornerRadius(12)
                        .padding(.horizontal)
                }

                Spacer()
            }
            .padding(.top, 60)
        }
        .ignoresSafeArea()
    }

    private var navTypeIcon: String {
        switch navManager.navType {
        case "pick": return "bag.fill"
        case "drop": return "house.fill"
        case "standby": return "location.circle"
        default: return "location"
        }
    }

    private var navTypeLabel: String {
        switch navManager.navType {
        case "pick": return "ピック先"
        case "drop": return "ドロップ先"
        case "standby": return "待機エリア"
        default: return "ナビ"
        }
    }

    private var markerColor: Color {
        switch navManager.navType {
        case "pick": return .green
        case "drop": return .red
        case "standby": return .blue
        default: return .orange
        }
    }
}
