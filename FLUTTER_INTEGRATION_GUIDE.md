# VenomX API - Flutter Integration Guide

## 📱 Overview
This guide explains how to integrate the VenomX FastAPI backend with your Flutter mobile app for snake identification and antivenom finding.

---

## 🔗 Base URL Configuration

```dart
class ApiConfig {
  // Development - Use your computer's local IP
  static const String DEV_BASE_URL = 'http://192.168.1.100:8000';
  
  // Production - Use your deployed server URL
  static const String PROD_BASE_URL = 'https://your-domain.com';
  
  // Use this in your app
  static const String BASE_URL = DEV_BASE_URL; // Change for production
}
```

### Finding Your Local IP:
**Windows (PowerShell):**
```powershell
ipconfig
# Look for "IPv4 Address" under your active network adapter
# Example: 192.168.1.100
```

**Important:** Use your computer's IP address, NOT `localhost` or `127.0.0.1` when testing from a real device!

---

## 🐍 1. Snake Identification Endpoint

### Endpoint: `POST /snake-id`

**Note:** There's also `POST /test-model` which does the same thing (used for testing)

### Request Format

```dart
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:io';

class SnakeIdentificationService {
  
  Future<Map<String, dynamic>> identifySnake(File imageFile) async {
    try {
      // Create multipart request
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('${ApiConfig.BASE_URL}/snake-id'),
      );
      
      // Add image file
      request.files.add(
        await http.MultipartFile.fromPath(
          'image',  // This must match the FastAPI parameter name
          imageFile.path,
        ),
      );
      
      // Send request
      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);
      
      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        throw Exception('Failed to identify snake: ${response.statusCode}');
      }
      
    } catch (e) {
      print('Error identifying snake: $e');
      rethrow;
    }
  }
}
```

### Response Format

```json
{
  "success": true,
  "snake_id": 5,
  "species": "Common Mock Viper",
  "scientific_name": "Psammodynastes pulverulentus",
  "confidence": 0.95,
  "fang_type": "rear-fanged",
  "danger_level": "mildly-venomous",
  "description": "A small, nocturnal snake commonly found in Southeast Asia...",
  "image_url": "https://example.com/snake-image.jpg",
  "bounding_box": {
    "x1": 120,
    "y1": 80,
    "x2": 450,
    "y2": 380
  }
}
```

### Flutter Model Class

```dart
class SnakeIdentificationResult {
  final bool success;
  final int? snakeId;
  final String? species;
  final String? scientificName;
  final double? confidence;
  final String? fangType;
  final String? dangerLevel;
  final String? description;
  final String? imageUrl;
  final BoundingBox? boundingBox;

  SnakeIdentificationResult({
    required this.success,
    this.snakeId,
    this.species,
    this.scientificName,
    this.confidence,
    this.fangType,
    this.dangerLevel,
    this.description,
    this.imageUrl,
    this.boundingBox,
  });

  factory SnakeIdentificationResult.fromJson(Map<String, dynamic> json) {
    return SnakeIdentificationResult(
      success: json['success'] ?? false,
      snakeId: json['snake_id'],
      species: json['species'],
      scientificName: json['scientific_name'],
      confidence: json['confidence']?.toDouble(),
      fangType: json['fang_type'],
      dangerLevel: json['danger_level'],
      description: json['description'],
      imageUrl: json['image_url'],
      boundingBox: json['bounding_box'] != null 
          ? BoundingBox.fromJson(json['bounding_box'])
          : null,
    );
  }
}

class BoundingBox {
  final int x1, y1, x2, y2;

  BoundingBox({
    required this.x1,
    required this.y1,
    required this.x2,
    required this.y2,
  });

  factory BoundingBox.fromJson(Map<String, dynamic> json) {
    return BoundingBox(
      x1: json['x1'],
      y1: json['y1'],
      x2: json['x2'],
      y2: json['y2'],
    );
  }
}
```

### Usage Example

```dart
// In your Flutter widget
class SnakeIdentificationPage extends StatefulWidget {
  @override
  _SnakeIdentificationPageState createState() => _SnakeIdentificationPageState();
}

class _SnakeIdentificationPageState extends State<SnakeIdentificationPage> {
  final SnakeIdentificationService _service = SnakeIdentificationService();
  SnakeIdentificationResult? _result;
  bool _isLoading = false;

  Future<void> _identifySnake(File imageFile) async {
    setState(() => _isLoading = true);
    
    try {
      final response = await _service.identifySnake(imageFile);
      final result = SnakeIdentificationResult.fromJson(response);
      
      setState(() {
        _result = result;
        _isLoading = false;
      });
      
      // Navigate to results page or show results
      if (result.success) {
        _showResults(result);
      } else {
        _showError('No snake detected in image');
      }
      
    } catch (e) {
      setState(() => _isLoading = false);
      _showError('Failed to identify snake: $e');
    }
  }

  void _showResults(SnakeIdentificationResult result) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(result.species ?? 'Unknown'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Scientific Name: ${result.scientificName}'),
            Text('Confidence: ${(result.confidence! * 100).toStringAsFixed(1)}%'),
            Text('Danger Level: ${result.dangerLevel}'),
            SizedBox(height: 10),
            Text(result.description ?? ''),
            if (result.imageUrl != null) ...[
              SizedBox(height: 10),
              Image.network(result.imageUrl!),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Close'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _findNearbyAntivenomFacilities(result);
            },
            child: Text('Find Antivenom'),
          ),
        ],
      ),
    );
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red),
    );
  }
}
```

---

## 🏥 2. Antivenom Finder Endpoint

### Endpoint: `POST /antivenom/finder`

### Request Format (Mobile App Use Case)

```dart
class AntivenomFinderService {
  
  Future<Map<String, dynamic>> findNearbyFacilities({
    required String snakeScientificName,
    required double latitude,
    required double longitude,
    double maxDistanceKm = 100.0,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('${ApiConfig.BASE_URL}/antivenom/finder'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'snake_scientific_name': snakeScientificName,
          'user_latitude': latitude,
          'user_longitude': longitude,
          'max_distance_km': maxDistanceKm,
        }),
      );
      
      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        throw Exception('Failed to find facilities: ${response.statusCode}');
      }
      
    } catch (e) {
      print('Error finding facilities: $e');
      rethrow;
    }
  }
}
```

### Response Format

```json
{
  "success": true,
  "message": "Found 5 facilities with antivenom for this snake",
  "total_facilities": 5,
  "facilities": [
    {
      "facility_id": 1,
      "facility_name": "Philippine General Hospital",
      "facility_type": "hospital",
      "region": "National Capital Region",
      "province": "Metro Manila",
      "city_municipality": "Manila",
      "address": "Taft Avenue, Ermita, Manila",
      "latitude": 14.5782,
      "longitude": 120.9847,
      "contact_number": "+63-2-554-8400",
      "facility_email": "pgh@up.edu.ph",
      "antivenom_name": "Philippine Polyvalent Anti-Snake Venom",
      "manufacturer": "RITM",
      "quantity": 25,
      "distance_km": 2.5,
      "estimated_travel_time_minutes": 12,
      "route_summary": "Via Taft Avenue"
    }
  ],
  "search_criteria": {
    "snake_scientific_name": "Psammodynastes pulverulentus",
    "user_location": [14.5995, 120.9842],
    "max_distance_km": 100
  }
}
```

### Flutter Model Class

```dart
class AntivenomFinderResult {
  final bool success;
  final String message;
  final int totalFacilities;
  final List<FacilityInfo> facilities;

  AntivenomFinderResult({
    required this.success,
    required this.message,
    required this.totalFacilities,
    required this.facilities,
  });

  factory AntivenomFinderResult.fromJson(Map<String, dynamic> json) {
    return AntivenomFinderResult(
      success: json['success'] ?? false,
      message: json['message'] ?? '',
      totalFacilities: json['total_facilities'] ?? 0,
      facilities: (json['facilities'] as List?)
          ?.map((f) => FacilityInfo.fromJson(f))
          .toList() ?? [],
    );
  }
}

class FacilityInfo {
  final int facilityId;
  final String facilityName;
  final String facilityType;
  final String region;
  final String province;
  final String cityMunicipality;
  final String? address;
  final double latitude;
  final double longitude;
  final String? contactNumber;
  final String? facilityEmail;
  final String? antivenomName;
  final String? manufacturer;
  final int? quantity;
  final double? distanceKm;
  final int? estimatedTravelTimeMinutes;
  final String? routeSummary;

  FacilityInfo({
    required this.facilityId,
    required this.facilityName,
    required this.facilityType,
    required this.region,
    required this.province,
    required this.cityMunicipality,
    this.address,
    required this.latitude,
    required this.longitude,
    this.contactNumber,
    this.facilityEmail,
    this.antivenomName,
    this.manufacturer,
    this.quantity,
    this.distanceKm,
    this.estimatedTravelTimeMinutes,
    this.routeSummary,
  });

  factory FacilityInfo.fromJson(Map<String, dynamic> json) {
    return FacilityInfo(
      facilityId: json['facility_id'],
      facilityName: json['facility_name'],
      facilityType: json['facility_type'],
      region: json['region'],
      province: json['province'],
      cityMunicipality: json['city_municipality'],
      address: json['address'],
      latitude: json['latitude'].toDouble(),
      longitude: json['longitude'].toDouble(),
      contactNumber: json['contact_number'],
      facilityEmail: json['facility_email'],
      antivenomName: json['antivenom_name'],
      manufacturer: json['manufacturer'],
      quantity: json['quantity'],
      distanceKm: json['distance_km']?.toDouble(),
      estimatedTravelTimeMinutes: json['estimated_travel_time_minutes'],
      routeSummary: json['route_summary'],
    );
  }
}
```

### Usage Example with Map Display

```dart
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';

class AntivenomMapPage extends StatefulWidget {
  final SnakeIdentificationResult snakeResult;

  AntivenomMapPage({required this.snakeResult});

  @override
  _AntivenomMapPageState createState() => _AntivenomMapPageState();
}

class _AntivenomMapPageState extends State<AntivenomMapPage> {
  final AntivenomFinderService _service = AntivenomFinderService();
  AntivenomFinderResult? _result;
  bool _isLoading = false;
  Position? _currentPosition;
  MapController _mapController = MapController();

  @override
  void initState() {
    super.initState();
    _getCurrentLocation();
  }

  Future<void> _getCurrentLocation() async {
    try {
      Position position = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );
      
      setState(() => _currentPosition = position);
      
      // Find nearby facilities
      await _findFacilities(position);
      
    } catch (e) {
      _showError('Failed to get location: $e');
    }
  }

  Future<void> _findFacilities(Position position) async {
    setState(() => _isLoading = true);
    
    try {
      final response = await _service.findNearbyFacilities(
        snakeScientificName: widget.snakeResult.scientificName!,
        latitude: position.latitude,
        longitude: position.longitude,
        maxDistanceKm: 100.0,
      );
      
      final result = AntivenomFinderResult.fromJson(response);
      
      setState(() {
        _result = result;
        _isLoading = false;
      });
      
      // Center map on user location
      _mapController.move(
        LatLng(position.latitude, position.longitude),
        13.0,
      );
      
    } catch (e) {
      setState(() => _isLoading = false);
      _showError('Failed to find facilities: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Nearby Antivenom Facilities'),
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator())
          : _result == null || _currentPosition == null
              ? Center(child: Text('Loading...'))
              : Column(
                  children: [
                    // Map view
                    Expanded(
                      flex: 2,
                      child: FlutterMap(
                        mapController: _mapController,
                        options: MapOptions(
                          center: LatLng(
                            _currentPosition!.latitude,
                            _currentPosition!.longitude,
                          ),
                          zoom: 13.0,
                        ),
                        children: [
                          TileLayer(
                            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                          ),
                          MarkerLayer(
                            markers: [
                              // User location marker
                              Marker(
                                point: LatLng(
                                  _currentPosition!.latitude,
                                  _currentPosition!.longitude,
                                ),
                                width: 80,
                                height: 80,
                                builder: (ctx) => Icon(
                                  Icons.person_pin_circle,
                                  color: Colors.blue,
                                  size: 40,
                                ),
                              ),
                              // Facility markers
                              ..._result!.facilities.map((facility) {
                                return Marker(
                                  point: LatLng(
                                    facility.latitude,
                                    facility.longitude,
                                  ),
                                  width: 80,
                                  height: 80,
                                  builder: (ctx) => GestureDetector(
                                    onTap: () => _showFacilityDetails(facility),
                                    child: Icon(
                                      Icons.local_hospital,
                                      color: Colors.red,
                                      size: 40,
                                    ),
                                  ),
                                );
                              }).toList(),
                            ],
                          ),
                        ],
                      ),
                    ),
                    // Facilities list
                    Expanded(
                      flex: 1,
                      child: _buildFacilitiesList(),
                    ),
                  ],
                ),
    );
  }

  Widget _buildFacilitiesList() {
    if (_result!.facilities.isEmpty) {
      return Center(
        child: Text('No facilities found within 100km'),
      );
    }

    return ListView.builder(
      itemCount: _result!.facilities.length,
      itemBuilder: (context, index) {
        final facility = _result!.facilities[index];
        return Card(
          margin: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          child: ListTile(
            leading: Icon(Icons.local_hospital, color: Colors.red),
            title: Text(facility.facilityName),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${facility.distanceKm?.toStringAsFixed(1)} km away'),
                Text('${facility.estimatedTravelTimeMinutes} min by car'),
                if (facility.quantity != null)
                  Text('Stock: ${facility.quantity} units'),
              ],
            ),
            trailing: IconButton(
              icon: Icon(Icons.directions),
              onPressed: () => _openDirections(facility),
            ),
            onTap: () => _showFacilityDetails(facility),
          ),
        );
      },
    );
  }

  void _showFacilityDetails(FacilityInfo facility) {
    showModalBottomSheet(
      context: context,
      builder: (context) => Container(
        padding: EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              facility.facilityName,
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 10),
            Text('📍 ${facility.address}'),
            Text('📞 ${facility.contactNumber ?? 'N/A'}'),
            Text('💉 ${facility.antivenomName ?? 'N/A'}'),
            Text('📦 Stock: ${facility.quantity ?? 0} units'),
            SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                ElevatedButton.icon(
                  icon: Icon(Icons.phone),
                  label: Text('Call'),
                  onPressed: () => _makeCall(facility.contactNumber),
                ),
                ElevatedButton.icon(
                  icon: Icon(Icons.directions),
                  label: Text('Directions'),
                  onPressed: () => _openDirections(facility),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _openDirections(FacilityInfo facility) {
    // Open in Google Maps or other mapping app
    // Implementation depends on your mapping solution
  }

  void _makeCall(String? phoneNumber) {
    // Implement phone call functionality
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red),
    );
  }
}
```

---

## 📦 Required Flutter Packages

Add these to your `pubspec.yaml`:

```yaml
dependencies:
  flutter:
    sdk: flutter
  
  # HTTP requests
  http: ^1.1.0
  
  # Location services
  geolocator: ^10.1.0
  permission_handler: ^11.0.1
  
  # Map display
  flutter_map: ^6.0.1
  latlong2: ^0.9.0
  
  # Image picker (for camera/gallery)
  image_picker: ^1.0.4
  
  # URL launcher (for phone calls, directions)
  url_launcher: ^6.2.1
```

---

## ⚙️ Android Permissions

Add to `android/app/src/main/AndroidManifest.xml`:

```xml
<manifest>
    <!-- Internet permission -->
    <uses-permission android:name="android.permission.INTERNET" />
    
    <!-- Location permissions -->
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
    
    <!-- Camera permission -->
    <uses-permission android:name="android.permission.CAMERA" />
    
    <!-- Storage permissions -->
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
    
    <application>
        ...
        <!-- Clear text traffic for local development -->
        android:usesCleartextTraffic="true"
        ...
    </application>
</manifest>
```

---

## 🔐 iOS Permissions

Add to `ios/Runner/Info.plist`:

```xml
<key>NSLocationWhenInUseUsageDescription</key>
<string>We need your location to find nearby antivenom facilities</string>

<key>NSCameraUsageDescription</key>
<string>We need camera access to identify snakes</string>

<key>NSPhotoLibraryUsageDescription</key>
<string>We need photo library access to select snake images</string>

<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>
```

---

## 🚀 Complete User Flow

```
1. User opens app
   ↓
2. User takes photo or selects from gallery
   ↓
3. App calls /snake-id with image
   ↓
4. Show snake identification results
   ↓
5. User taps "Find Antivenom"
   ↓
6. App gets current location (GPS)
   ↓
7. App calls /antivenom/finder with:
   - snake_scientific_name
   - user GPS coordinates
   ↓
8. Display facilities on map with markers
   ↓
9. User can:
   - View facility details
   - Call facility
   - Get directions
```

---

## 🐛 Error Handling Best Practices

```dart
class ApiService {
  
  Future<T> handleApiCall<T>(Future<T> Function() apiCall) async {
    try {
      return await apiCall();
    } on SocketException {
      throw ApiException('No internet connection');
    } on HttpException {
      throw ApiException('Server error');
    } on FormatException {
      throw ApiException('Invalid response format');
    } catch (e) {
      throw ApiException('Unexpected error: $e');
    }
  }
}

class ApiException implements Exception {
  final String message;
  ApiException(this.message);
  
  @override
  String toString() => message;
}
```

---

## 📝 Key Points to Remember

1. **Use your computer's IP address** (not localhost) when testing from physical device
2. **Request location permissions** before calling antivenom finder
3. **Compress images** before sending to reduce upload time
4. **Handle loading states** - snake identification can take 2-5 seconds
5. **Cache results** to avoid unnecessary API calls
6. **Test with real snake images** to ensure detection works
7. **Handle "no snake detected"** scenario gracefully
8. **Show confidence scores** to users for transparency
9. **Validate internet connection** before API calls
10. **Use HTTPS in production** for security

---

## 🔄 Typical API Response Times

- **Snake Identification**: 2-5 seconds (depends on image size)
- **Antivenom Finder**: 1-3 seconds (depends on number of facilities)
- **Network latency**: +500ms-2s (on mobile data)

**Tip**: Show loading indicators and progress feedback to users!

---

## 📞 Support

For issues or questions:
- Check server logs: `python main.py`
- Test endpoints in browser: `http://localhost:8000/docs`
- Verify network connectivity from mobile device
