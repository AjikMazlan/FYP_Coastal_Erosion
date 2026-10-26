import 'package:flutter/material.dart';

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'shoreline_prediction_screen.dart';

import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

const String coastalApiBaseUrl = 'http://127.0.0.1:5000';
void main() {
  runApp(const CoastalErosionApp());
}

class CoastalErosionApp extends StatelessWidget {
  const CoastalErosionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Coastal Watch',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme:
            ColorScheme.fromSeed(
              seedColor: const Color(0xFF36D6BE),
              brightness: Brightness.dark,
            ).copyWith(
              primary: const Color(0xFF36D6BE),
              onPrimary: const Color(0xFF062D29),
              surface: const Color(0xFF152238),
              onSurface: const Color(0xFFF0F5FA),
            ),
        scaffoldBackgroundColor: const Color(0xFF0B1425),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0B1425),
          foregroundColor: Color(0xFFF0F5FA),
          elevation: 0,
          scrolledUnderElevation: 0,
        ),
        dividerColor: const Color(0xFF29384D),
      ),
      home: const HomeScreen(),
    );
  }
}

// LOGIN SCREEN
class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(28),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const CircleAvatar(
                  radius: 48,
                  backgroundColor: Color(0xFFD8F1F3),
                  child: Icon(Icons.waves, size: 52, color: Color(0xFF087E8B)),
                ),
                const SizedBox(height: 24),
                const Text(
                  'Coastal Erosion',
                  style: TextStyle(fontSize: 29, fontWeight: FontWeight.bold),
                ),
                const Text(
                  'Risk Assessment & Prediction',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 16, color: Colors.blueGrey),
                ),
                const SizedBox(height: 45),
                const TextField(
                  decoration: InputDecoration(
                    labelText: 'Email',
                    prefixIcon: Icon(Icons.email_outlined),
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                const TextField(
                  obscureText: true,
                  decoration: InputDecoration(
                    labelText: 'Password',
                    prefixIcon: Icon(Icons.lock_outline),
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: () {
                      Navigator.pushReplacement(
                        context,
                        MaterialPageRoute(
                          builder: (context) => const HomeScreen(),
                        ),
                      );
                    },
                    child: const Text('Login (Demo)'),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () {
                      Navigator.pushReplacement(
                        context,
                        MaterialPageRoute(
                          builder: (context) => const HomeScreen(),
                        ),
                      );
                    },
                    child: const Text('Preview Application'),
                  ),
                ),
                const SizedBox(height: 20),
                const Text(
                  'Prototype UI - Authentication not connected',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey, fontSize: 12),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// HOME SCREEN
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          children: [
            Icon(Icons.waves, color: Color(0xFF36D6BE)),
            SizedBox(width: 10),
            Text(
              'COASTAL WATCH',
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.bold,
                letterSpacing: 2,
              ),
            ),
          ],
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [Color(0xFF164D50), Color(0xFF152238)],
                ),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: const Color(0xFF2B6265)),
              ),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.waves, color: Color(0xFF36D6BE), size: 44),
                  SizedBox(height: 20),
                  Text(
                    'TERENGGANU COASTLINE',
                    style: TextStyle(
                      color: Color(0xFF72E8D5),
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 2,
                    ),
                  ),
                  SizedBox(height: 10),
                  Text(
                    'Understand your\ncoastal risk.',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 30,
                      height: 1.15,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  SizedBox(height: 14),
                  Text(
                    'Explore coastal erosion risk and estimated '
                    'shoreline movement along Terengganu.',
                    style: TextStyle(
                      color: Color(0xFFB9CCD5),
                      fontSize: 14,
                      height: 1.6,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 28),
            const Text(
              'Explore your coastline',
              style: TextStyle(fontSize: 21, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            const Text(
              'Choose coastal risk assessment or shoreline prediction.',
              style: TextStyle(color: Color(0xFFA8B8CC), fontSize: 14),
            ),
            const SizedBox(height: 20),
            FeatureCard(
              title: 'Coastal Risk Map',
              subtitle: 'Explore coastal erosion risk across Terengganu',
              icon: Icons.map_outlined,
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const CoastalRiskMapScreen(),
                  ),
                );
              },
            ),
            FeatureCard(
              title: 'Shoreline Prediction',
              subtitle: 'Explore shoreline projections for 1–10 years',
              icon: Icons.trending_down,
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const ShorelinePredictionScreen(
                      baseUrl: coastalApiBaseUrl,
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

// NAVIGATION HELPER
void openFeature(BuildContext context, String title, String description) {
  Navigator.push(
    context,
    MaterialPageRoute(
      builder: (context) =>
          FeatureScreen(title: title, description: description),
    ),
  );
}

// FEATURE CARD
class FeatureCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final VoidCallback onTap;

  const FeatureCard({
    super.key,
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF152238),
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 14),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: Color(0xFF29384D)),
      ),
      clipBehavior: Clip.antiAlias,
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 12,
        ),
        leading: Container(
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            color: const Color(0xFF193C43),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Icon(icon, color: const Color(0xFF36D6BE), size: 25),
        ),
        title: Text(
          title,
          style: const TextStyle(
            color: Color(0xFFF0F5FA),
            fontSize: 15,
            fontWeight: FontWeight.w600,
          ),
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(
            subtitle,
            style: const TextStyle(
              color: Color(0xFFA8B8CC),
              fontSize: 12,
              height: 1.5,
            ),
          ),
        ),
        trailing: const Icon(
          Icons.chevron_right,
          color: Color(0xFF36D6BE),
          size: 22,
        ),
        onTap: onTap,
      ),
    );
  }
}

// PLACEHOLDER FEATURE SCREEN
class FeatureScreen extends StatelessWidget {
  final String title;
  final String description;

  const FeatureScreen({
    super.key,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            description,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 18),
          ),
        ),
      ),
    );
  }
}

class ModelTestScreen extends StatefulWidget {
  const ModelTestScreen({super.key});

  @override
  State<ModelTestScreen> createState() => _ModelTestScreenState();
}

class _ModelTestScreenState extends State<ModelTestScreen> {
  Map<String, dynamic>? result;
  String? errorMessage;
  bool isLoading = false;
  int selectedYears = 10;

  final TextEditingController transectController = TextEditingController(
    text: '2',
  );

  @override
  void dispose() {
    transectController.dispose();
    super.dispose();
  }

  Future<void> testModel(int transectId) async {
    setState(() {
      isLoading = true;
      result = null;
      errorMessage = null;
    });

    try {
      // Android Emulator accesses PC localhost via 10.0.2.2
      final url = Uri.parse(
        '$coastalApiBaseUrl/assessment'
        '?transect_id=$transectId&years=$selectedYears',
      );

      final response = await http.get(url).timeout(const Duration(seconds: 15));

      final body = jsonDecode(response.body);

      if (response.statusCode != 200) {
        throw Exception(body['error'] ?? 'API request failed');
      }

      if (!mounted) return;

      setState(() {
        result = Map<String, dynamic>.from(body);
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        errorMessage = e.toString();
      });
    } finally {
      if (mounted) {
        setState(() => isLoading = false);
      }
    }
  }

  String formatNumber(dynamic value) {
    if (value == null) return 'Not available';
    if (value is num) return value.toStringAsFixed(2);
    return value.toString();
  }

  Color riskColor(String risk) {
    switch (risk) {
      case 'Critical':
        return Colors.red;
      case 'Warning':
        return Colors.orange;
      case 'Stable':
        return Colors.green;
      default:
        return Colors.blueGrey;
    }
  }

  Widget resultRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: Colors.blueGrey)),
          Text(
            value,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ML Assessment')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Text(
            'Coastal Erosion Model Test',
            style: TextStyle(fontSize: 23, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text('Live results from the Flask backend.'),
          const SizedBox(height: 24),

          const Text(
            'Prediction Horizon',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),

          DropdownButton<int>(
            value: selectedYears,
            isExpanded: true,
            items: [1, 5, 10].map((year) {
              return DropdownMenuItem(value: year, child: Text('$year years'));
            }).toList(),
            onChanged: isLoading
                ? null
                : (value) {
                    if (value != null) {
                      setState(() => selectedYears = value);
                    }
                  },
          ),

          const SizedBox(height: 14),

          const Text(
            'Select Coastal Location',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),

          const SizedBox(height: 10),

          TextField(
            controller: transectController,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'Coastal Point ID',
              hintText: 'Enter ID from 1 to 2775',
              prefixIcon: Icon(Icons.location_on_outlined),
              border: OutlineInputBorder(),
            ),
          ),

          const SizedBox(height: 12),

          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: isLoading
                  ? null
                  : () {
                      final id = int.tryParse(transectController.text.trim());

                      if (id == null || id < 1 || id > 2775) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Please enter a valid ID (1-2775)'),
                          ),
                        );
                        return;
                      }

                      testModel(id);
                    },
              icon: const Icon(Icons.search),
              label: const Text('Assess Coastal Location'),
            ),
          ),

          const SizedBox(height: 20),

          FilledButton(
            onPressed: isLoading ? null : () => testModel(1),
            child: const Text('Test Original JPS Point 1'),
          ),

          const SizedBox(height: 10),

          FilledButton(
            onPressed: isLoading ? null : () => testModel(2),
            child: const Text('Test Interpolated Point 2 + LR'),
          ),

          const SizedBox(height: 20),

          if (isLoading) const Center(child: CircularProgressIndicator()),

          if (errorMessage != null)
            Card(
              color: Colors.red.shade50,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  'Connection error:\n$errorMessage',
                  style: const TextStyle(color: Colors.red),
                ),
              ),
            ),

          if (result != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Assessment Result',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),

                    const Divider(),

                    resultRow('Location', '${result!['location']}'),

                    resultRow('Coastal Cell', '${result!['coastal_cell']}'),

                    resultRow('Data Source', '${result!['source_type']}'),

                    const SizedBox(height: 12),

                    const Text(
                      'K-Means Risk Classification',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),

                    const SizedBox(height: 5),

                    Text(
                      '${result!['risk_label']}',
                      style: TextStyle(
                        fontSize: 27,
                        fontWeight: FontWeight.bold,
                        color: riskColor('${result!['risk_label']}'),
                      ),
                    ),

                    const Divider(height: 32),

                    const Text(
                      'Primary Shoreline Projection',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),

                    resultRow(
                      'Projection Source',
                      '${result!['projection_source']}',
                    ),

                    resultRow(
                      'Annual Erosion Rate',
                      '${formatNumber(result!['primary_rate_m_yr'])} m/year',
                    ),

                    resultRow(
                      'Estimated Retreat',
                      '${formatNumber(result!['primary_retreat_m'])} m',
                    ),

                    const Divider(height: 32),

                    const Text(
                      'Linear Regression (Experimental)',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),

                    resultRow(
                      'Predicted Erosion Rate',
                      '${formatNumber(result!['lr_experimental_rate_m_yr'])} m/year',
                    ),

                    resultRow(
                      'Estimated LR Retreat',
                      '${formatNumber(result!['lr_experimental_retreat_m'])} m',
                    ),

                    const SizedBox(height: 15),

                    const Text(
                      'Note: These are estimated movement '
                      'distances, not mapped future shoreline '
                      'positions. LR predictions are experimental.',
                      style: TextStyle(fontSize: 12, color: Colors.blueGrey),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class CoastalRiskMapScreen extends StatefulWidget {
  const CoastalRiskMapScreen({super.key});

  @override
  State<CoastalRiskMapScreen> createState() => _CoastalRiskMapScreenState();
}

class _CoastalRiskMapScreenState extends State<CoastalRiskMapScreen> {
  List<Map<String, dynamic>> _points = [];
  List<Marker> _markers = [];
  List<Polyline> _riskLines = [];
  bool _showRiskLines = true;

  bool _loading = true;
  bool _includeInterpolated = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadLocations();
  }

  Color _riskColor(String risk) {
    switch (risk) {
      case 'Stable':
        return const Color(0xFF22C55E);
      case 'Warning':
        return const Color(0xFFF59E0B);
      case 'Critical':
        return const Color(0xFFEF4444);
      default:
        return const Color(0xFF94A3B8);
    }
  }

  IconData _riskIcon(String risk) {
    switch (risk) {
      case 'Stable':
        return Icons.check;
      case 'Warning':
        return Icons.warning_amber_rounded;
      case 'Critical':
        return Icons.priority_high;
      case 'Protected':
        return Icons.shield_outlined;
      default:
        return Icons.location_on_outlined;
    }
  }

  Future<void> _loadLocations() async {
    setState(() {
      _loading = true;
      _error = null;
      _points = [];
      _markers = [];
      _riskLines = [];
    });

    try {
      final response = await http
          .get(Uri.parse('$coastalApiBaseUrl/locations'))
          .timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}');
      }

      final body = jsonDecode(response.body) as Map<String, dynamic>;

      final loaded = (body['locations'] as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();

      if (!mounted) return;

      setState(() {
        _points = loaded;
        _markers = _createMarkers();
        _riskLines = _createRiskLines();
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _error = 'Could not load coastal locations.\n$e';
      });
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  List<Marker> _createMarkers() {
    final visible = _points.where(
      (point) => _includeInterpolated || point['source_type'] == 'JPS_Original',
    );

    return visible.map((point) {
      return Marker(
        point: LatLng(
          (point['latitude'] as num).toDouble(),
          (point['longitude'] as num).toDouble(),
        ),
        width: 28,
        height: 28,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => _showDetails(point),
          child: Center(
            child: Icon(
              _riskIcon('${point['risk_label']}'),
              color: _riskColor('${point['risk_label']}'),
              size: 24,
              shadows: const [
                Shadow(color: Colors.black, offset: Offset(-0.8, 0)),
                Shadow(color: Colors.black, offset: Offset(0.8, 0)),
                Shadow(color: Colors.black, offset: Offset(0, -0.8)),
                Shadow(color: Colors.black, offset: Offset(0, 0.8)),
              ],
            ),
          ),
        ),
      );
    }).toList();
  }

  List<Polyline> _createRiskLines() {
    final ordered = List<Map<String, dynamic>>.from(_points)
      ..sort(
        (a, b) => (a['transect_id'] as num).compareTo(b['transect_id'] as num),
      );

    const distance = Distance();
    const maxLinkDistanceMeters = 100.0;

    final lines = <Polyline>[];
    var segment = <LatLng>[];
    var segmentRisk = '';

    void saveSegment() {
      if (segment.length >= 2) {
        lines.add(
          Polyline(
            points: List<LatLng>.from(segment),
            color: _riskColor(segmentRisk),
            strokeWidth: 4,
            borderColor: Colors.black,
            borderStrokeWidth: 0.6,
          ),
        );
      }

      segment = [];
    }

    for (var i = 1; i < ordered.length; i++) {
      final previous = ordered[i - 1];
      final current = ordered[i];

      final from = LatLng(
        (previous['latitude'] as num).toDouble(),
        (previous['longitude'] as num).toDouble(),
      );

      final to = LatLng(
        (current['latitude'] as num).toDouble(),
        (current['longitude'] as num).toDouble(),
      );

      final risk = '${previous['risk_label']}';

      final consecutiveIds =
          (current['transect_id'] as num) - (previous['transect_id'] as num) ==
          1;

      final sameCell = previous['coastal_cell'] == current['coastal_cell'];

      final sameRisk = previous['risk_label'] == current['risk_label'];

      final hasRiskCategory = ['Stable', 'Warning', 'Critical'].contains(risk);

      final canConnect =
          consecutiveIds &&
          sameCell &&
          sameRisk &&
          hasRiskCategory &&
          distance(from, to) <= maxLinkDistanceMeters;

      if (!canConnect) {
        saveSegment();
        continue;
      }

      if (segment.isEmpty) {
        segmentRisk = risk;
        segment.add(from);
      }

      segment.add(to);
    }

    saveSegment();
    return lines;
  }

  void _showDetails(Map<String, dynamic> point) {
    final risk = '${point['risk_label']}';
    final rate = point['primary_rate_m_yr'];
    final source = '${point['source_type']}'.replaceAll('_', ' ');
    final projection = '${point['projection_source']}'.replaceAll('_', ' ');

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: const Color(0xFF152238),
      builder: (context) {
        return SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${point['location']}',
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '${point['district']} • ${point['coastal_cell']}',
                style: const TextStyle(color: Color(0xFFA8B8CC)),
              ),
              const SizedBox(height: 20),
              Text(
                risk,
                style: TextStyle(
                  color: _riskColor(risk),
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              Text('Coastal Point ID: ${point['transect_id']}'),
              const SizedBox(height: 10),
              Text('Point source: $source'),
              const SizedBox(height: 10),
              Text(
                rate is num
                    ? 'Annual erosion rate: '
                          '${rate.toStringAsFixed(2)} m/year'
                    : 'Annual erosion rate: Not available',
              ),
              const SizedBox(height: 10),
              Text('Rate source: $projection'),
              const SizedBox(height: 16),
              const Text(
                'Risk categories are based on the project dataset. '
                'Interpolated points are estimates between JPS locations.',
                style: TextStyle(
                  color: Color(0xFFA8B8CC),
                  fontSize: 12,
                  height: 1.5,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Coastal Risk Map'),
        actions: [
          IconButton(
            tooltip: 'Search by point ID',
            icon: const Icon(Icons.search),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => const ModelTestScreen(),
                ),
              );
            },
          ),
          IconButton(
            tooltip: 'Reload locations',
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _loadLocations,
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              child: Wrap(
                spacing: 14,
                runSpacing: 8,
                children: [
                  for (final risk in [
                    'Stable',
                    'Warning',
                    'Critical',
                    'Protected',
                  ])
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.circle, color: _riskColor(risk), size: 10),
                        const SizedBox(width: 5),
                        Text(risk, style: const TextStyle(fontSize: 12)),
                      ],
                    ),
                ],
              ),
            ),
            SwitchListTile(
              dense: true,
              title: const Text('Show interpolated markers'),
              subtitle: Text(
                '${_markers.length} shown • '
                '${_points.length} locations loaded',
              ),
              value: _includeInterpolated,
              onChanged: _loading
                  ? null
                  : (value) {
                      setState(() {
                        _includeInterpolated = value;
                        _markers = _createMarkers();
                      });
                    },
            ),
            SwitchListTile(
              dense: true,
              title: const Text('Show estimated risk lines'),
              subtitle: const Text('Uses original and interpolated points'),
              value: _showRiskLines,
              onChanged: (value) {
                setState(() => _showRiskLines = value);
              },
            ),
            if (_loading) const LinearProgressIndicator(),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  _error!,
                  style: const TextStyle(color: Color(0xFFFFB4AB)),
                ),
              ),
            Expanded(
              child: FlutterMap(
                options: const MapOptions(
                  initialCenter: LatLng(5.10, 103.15),
                  initialZoom: 8,
                  minZoom: 5,
                  maxZoom: 19,
                ),
                children: [
                  TileLayer(
                    urlTemplate:
                        'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'my.uitm.izzul.coastal_erosion_fyp',
                    maxNativeZoom: 19,
                  ),
                  if (_showRiskLines)
                    IgnorePointer(child: PolylineLayer(polylines: _riskLines)),
                  MarkerLayer(markers: _markers),
                  SimpleAttributionWidget(
                    source: const Text(
                      'OpenStreetMap contributors',
                      style: TextStyle(color: Color(0xFF152238), fontSize: 11),
                    ),
                    backgroundColor: Colors.white,
                    onTap: () => launchUrl(
                      Uri.parse('https://www.openstreetmap.org/copyright'),
                      mode: LaunchMode.externalApplication,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
