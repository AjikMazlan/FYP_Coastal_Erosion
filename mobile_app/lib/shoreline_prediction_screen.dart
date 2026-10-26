import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

class ShorelinePredictionScreen extends StatefulWidget {
  final String baseUrl;

  const ShorelinePredictionScreen({super.key, required this.baseUrl});

  @override
  State<ShorelinePredictionScreen> createState() =>
      _ShorelinePredictionScreenState();
}

class _ShorelinePredictionScreenState extends State<ShorelinePredictionScreen> {
  static const _referenceColor = Color(0xFF2563EB);
  static const _predictionColor = Color(0xFFF97316);

  int _selectedYear = 2025;
  int _referenceYear = 2024;

  bool _loading = true;
  String? _error;

  List<Map<String, dynamic>> _transects = [];

  @override
  void initState() {
    super.initState();
    _loadPrediction();
  }

  Future<void> _loadPrediction() async {
    final requestedYear = _selectedYear;

    setState(() {
      _loading = true;
      _error = null;
      _transects = [];
    });

    try {
      final response = await http
          .get(
            Uri.parse(
              '${widget.baseUrl}/shoreline-prediction'
              '?year=$requestedYear',
            ),
          )
          .timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }

      final body = jsonDecode(response.body) as Map<String, dynamic>;

      final records = (body['transects'] as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();

      records.sort(
        (a, b) => (a['transect_id'] as num).compareTo(b['transect_id'] as num),
      );

      if (records.length != 4 ||
          (body['forecast_year'] as num).toInt() != requestedYear) {
        throw const FormatException(
          'Unexpected shoreline prediction response.',
        );
      }

      if (!mounted) return;

      setState(() {
        _referenceYear = (body['reference_year'] as num).toInt();
        _transects = records;
      });
    } catch (error) {
      debugPrint('Shoreline prediction error: $error');

      if (!mounted) return;

      setState(() {
        _error =
            'Unable to load the prediction. '
            'Check your connection and try again.';
      });
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  LatLng _mapPoint(Map<String, dynamic> transect, String field) {
    final point = transect[field] as Map;

    return LatLng(
      (point['latitude'] as num).toDouble(),
      (point['longitude'] as num).toDouble(),
    );
  }

  Widget _measurement(String label, num value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(child: Text(label)),
          Text(
            '${value.toStringAsFixed(2)} m',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }

  void _showDetails(Map<String, dynamic> transect) {
    final predictedPoint = transect['predicted_point'] as Map;
    final outside = predictedPoint['outside_transect'] == true;

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (sheetContext) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Kuala Merang • Transect '
                  '${transect['transect_id']}',
                  style: Theme.of(sheetContext).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                const Text('Position measured from the transect origin.'),
                const SizedBox(height: 12),
                _measurement(
                  'Reference ($_referenceYear)',
                  transect['reference_position_m'] as num,
                ),
                _measurement(
                  'Prediction ($_selectedYear)',
                  transect['predicted_position_m'] as num,
                ),
                _measurement(
                  'Change along transect',
                  transect['change_from_reference_m'] as num,
                ),
                const SizedBox(height: 12),
                const Text(
                  'A negative change indicates movement '
                  'toward the transect origin.',
                ),
                if (outside) ...[
                  const SizedBox(height: 12),
                  const Text(
                    'This prediction extends beyond the '
                    'surveyed transect.',
                    style: TextStyle(
                      color: Color(0xFFF59E0B),
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  Marker _marker(Map<String, dynamic> transect, {required bool predicted}) {
    return Marker(
      point: _mapPoint(
        transect,
        predicted ? 'predicted_point' : 'reference_point',
      ),
      width: 40,
      height: 40,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => _showDetails(transect),
        child: Center(
          child: Icon(
            predicted ? Icons.diamond : Icons.add_box_rounded,
            color: predicted ? _predictionColor : _referenceColor,
            size: 23,
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
  }

  Widget _legend(String text, Color color, IconData icon) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: color, size: 26),
        const SizedBox(width: 6),
        Text(text),
      ],
    );
  }

  void _showPredictionSummary() {
    final hasOutside = _transects.any(
      (row) => (row['predicted_point'] as Map)['outside_transect'] == true,
    );

    String signedValue(num value) {
      final prefix = value > 0 ? '+' : '';
      return '$prefix${value.toStringAsFixed(2)}';
    }

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (sheetContext) {
        return SafeArea(
          child: SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Prediction Summary',
                    style: Theme.of(sheetContext).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Kuala Merang • $_selectedYear',
                    style: Theme.of(sheetContext).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Experimental • Linear Regression',
                    style: TextStyle(fontSize: 12),
                  ),
                  const SizedBox(height: 16),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: DataTable(
                      horizontalMargin: 8,
                      columnSpacing: 18,
                      columns: [
                        const DataColumn(label: Text('Transect')),
                        DataColumn(
                          numeric: true,
                          label: Text('$_referenceYear\n(m)'),
                        ),
                        DataColumn(
                          numeric: true,
                          label: Text('$_selectedYear\n(m)'),
                        ),
                        const DataColumn(
                          numeric: true,
                          label: Text('Change\n(m)'),
                        ),
                      ],
                      rows: _transects.map((row) {
                        final reference = row['reference_position_m'] as num;
                        final predicted = row['predicted_position_m'] as num;
                        final change = row['change_from_reference_m'] as num;

                        final outside =
                            (row['predicted_point']
                                as Map)['outside_transect'] ==
                            true;

                        return DataRow(
                          cells: [
                            DataCell(Text('T${row['transect_id']}')),
                            DataCell(Text(reference.toStringAsFixed(2))),
                            DataCell(
                              Text(
                                '${predicted.toStringAsFixed(2)}'
                                '${outside ? ' *' : ''}',
                              ),
                            ),
                            DataCell(
                              Text(
                                signedValue(change),
                                style: const TextStyle(
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                          ],
                        );
                      }).toList(),
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Positions are measured from each transect origin.\n\n'
                    'Change = predicted position − reference position. '
                    'A negative change indicates movement toward '
                    'the transect origin.',
                    style: TextStyle(fontSize: 12),
                  ),
                  if (hasOutside) ...[
                    const SizedBox(height: 12),
                    const Text(
                      '* Prediction extends beyond the surveyed transect.',
                      style: TextStyle(color: Color(0xFFF59E0B), fontSize: 12),
                    ),
                  ],
                  const SizedBox(height: 16),
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton(
                      onPressed: () => Navigator.pop(sheetContext),
                      child: const Text('Close'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildContent() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: _loadPrediction,
                child: const Text('Try again'),
              ),
            ],
          ),
        ),
      );
    }

    final referencePoints = _transects
        .map((row) => _mapPoint(row, 'reference_point'))
        .toList();

    final predictedPoints = _transects
        .map((row) => _mapPoint(row, 'predicted_point'))
        .toList();

    final outsideCount = _transects.where((row) {
      final point = row['predicted_point'] as Map;
      return point['outside_transect'] == true;
    }).length;

    return Column(
      children: [
        Expanded(
          child: FlutterMap(
            key: ValueKey(_selectedYear),
            options: MapOptions(
              initialCameraFit: CameraFit.bounds(
                bounds: LatLngBounds.fromPoints([
                  ...referencePoints,
                  ...predictedPoints,
                ]),
                padding: const EdgeInsets.all(36),
                maxZoom: 17,
              ),
              minZoom: 5,
              maxZoom: 19,
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'my.uitm.izzul.coastal_erosion_fyp',
                maxNativeZoom: 19,
              ),
              IgnorePointer(
                child: PolylineLayer(
                  polylines: [
                    Polyline(
                      points: referencePoints,
                      color: _referenceColor,
                      strokeWidth: 4,
                      borderColor: Colors.black,
                      borderStrokeWidth: 0.7,
                    ),
                    Polyline(
                      points: predictedPoints,
                      color: _predictionColor,
                      strokeWidth: 4,
                      borderColor: Colors.black,
                      borderStrokeWidth: 0.7,
                      pattern: StrokePattern.dashed(segments: [12, 8]),
                    ),
                  ],
                ),
              ),
              MarkerLayer(
                markers: [
                  for (final row in _transects) _marker(row, predicted: false),
                  for (final row in _transects) _marker(row, predicted: true),
                ],
              ),
              SimpleAttributionWidget(
                source: const Text(
                  'OpenStreetMap contributors',
                  style: TextStyle(color: Colors.black87, fontSize: 11),
                ),
                backgroundColor: Colors.white,
                onTap: () {
                  launchUrl(
                    Uri.parse('https://www.openstreetmap.org/copyright'),
                    mode: LaunchMode.externalApplication,
                  );
                },
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            children: [
              OutlinedButton.icon(
                onPressed: _showPredictionSummary,
                icon: const Icon(Icons.table_chart_outlined),
                label: const Text('View prediction summary'),
              ),
              const SizedBox(height: 8),
              const Text(
                'Experimental • Four transects\n'
                'Lines connect transect points to approximate '
                'the shoreline. Tap a symbol for details.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12),
              ),
              if (outsideCount > 0) ...[
                const SizedBox(height: 6),
                Text(
                  '$outsideCount prediction extends beyond '
                  'the surveyed transect.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Color(0xFFF59E0B),
                    fontSize: 12,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Shoreline Prediction'),
        actions: [
          IconButton(
            tooltip: 'Refresh prediction',
            onPressed: _loading ? null : _loadPrediction,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Kuala Merang',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                      ),
                      DropdownButton<int>(
                        value: _selectedYear,
                        items: List.generate(10, (index) {
                          final yearsAhead = index + 1;
                          final year = _referenceYear + yearsAhead;
                          final unit = yearsAhead == 1 ? 'year' : 'years';

                          return DropdownMenuItem<int>(
                            value: year,
                            child: Text('$year (+$yearsAhead $unit)'),
                          );
                        }),
                        onChanged: _loading
                            ? null
                            : (year) {
                                if (year == null || year == _selectedYear) {
                                  return;
                                }

                                _selectedYear = year;
                                _loadPrediction();
                              },
                      ),
                    ],
                  ),
                  const Text(
                    'Linear Regression • Trained through 2024',
                    style: TextStyle(fontSize: 12),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 18,
                    runSpacing: 6,
                    children: [
                      _legend(
                        '$_referenceYear reference',
                        _referenceColor,
                        Icons.horizontal_rule,
                      ),
                      _legend(
                        '$_selectedYear prediction',
                        _predictionColor,
                        Icons.more_horiz,
                      ),
                    ],
                  ),
                ],
              ),
            ),
            Expanded(child: _buildContent()),
          ],
        ),
      ),
    );
  }
}
