import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

// Location information supplied by Flask.
class _ForecastSite {
  final String id;
  final String name;
  final int referenceYear;
  final int firstYear;
  final int lastYear;
  final int transectCount;
  final String qualityWarning;

  const _ForecastSite({
    required this.id,
    required this.name,
    required this.referenceYear,
    required this.firstYear,
    required this.lastYear,
    required this.transectCount,
    required this.qualityWarning,
  });

  factory _ForecastSite.fromJson(Map<String, dynamic> json) {
    final site = _ForecastSite(
      id: json['site_id'] as String,
      name: json['site'] as String,
      referenceYear: (json['reference_year'] as num).toInt(),
      firstYear: (json['first_forecast_year'] as num).toInt(),
      lastYear: (json['last_forecast_year'] as num).toInt(),
      transectCount: (json['transect_count'] as num).toInt(),
      qualityWarning: json['quality_warning']?.toString() ?? '',
    );

    if (site.id.isEmpty ||
        site.name.isEmpty ||
        site.transectCount < 1 ||
        site.firstYear != site.referenceYear + 1 ||
        site.lastYear != site.referenceYear + 10) {
      throw const FormatException('Invalid shoreline location');
    }

    return site;
  }
}

class ShorelinePredictionScreen extends StatefulWidget {
  final String baseUrl;

  const ShorelinePredictionScreen({super.key, required this.baseUrl});

  @override
  State<ShorelinePredictionScreen> createState() =>
      _ShorelinePredictionScreenState();
}

class _ShorelinePredictionScreenState extends State<ShorelinePredictionScreen> {
  static const _accent = Color(0xFF36D6BE);
  static const _panel = Color(0xFF152238);
  static const _muted = Color(0xFFA8B8CC);
  static const _border = Color(0xFF29384D);

  static const _referenceColors = {
    'Blue': Color(0xFF60A5FA),
    'Cyan': Color(0xFF22D3EE),
    'Purple': Color(0xFFC084FC),
    'Green': Color(0xFF4ADE80),
  };

  static const _predictionColors = {
    'Orange': Color(0xFFFB923C),
    'Yellow': Color(0xFFFACC15),
    'Pink': Color(0xFFF472B6),
    'Red': Color(0xFFF87171),
  };

  final MapController _mapController = MapController();

  Color _referenceColor = _referenceColors['Blue']!;
  Color _predictionColor = _predictionColors['Orange']!;

  double _lineWidth = 4;

  bool _showReference = true;
  bool _showPrediction = true;
  bool _dashedPrediction = true;
  bool _loading = true;
  bool _mapReady = false;

  List<_ForecastSite> _sites = [];
  List<Map<String, dynamic>> _transects = [];

  String _siteId = 'kuala_merang';
  String _site = 'Kuala Merang';
  String _qualityWarning = '';
  String _qcStatus = 'UNVALIDATED';

  int _referenceYear = 2024;
  int _forecastYear = 2025;
  int? _requestedYear;
  int _requestNumber = 0;

  String? _error;
  Map<String, dynamic>? _evaluation;

  @override
  void initState() {
    super.initState();
    _loadSitesAndPrediction();
  }

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  // LOAD AVAILABLE LOCATIONS

  Future<void> _loadSitesAndPrediction() async {
    final requestNumber = ++_requestNumber;

    setState(() {
      _loading = true;
      _mapReady = false;
      _error = null;
      _transects = [];
    });

    try {
      final response = await http
          .get(Uri.parse('${widget.baseUrl}/shoreline-sites'))
          .timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) {
        throw Exception('Location list: HTTP ${response.statusCode}');
      }

      final body = jsonDecode(response.body) as Map<String, dynamic>;

      final sites = (body['sites'] as List)
          .map(
            (item) =>
                _ForecastSite.fromJson(Map<String, dynamic>.from(item as Map)),
          )
          .toList();

      if (sites.isEmpty ||
          sites.map((site) => site.id).toSet().length != sites.length) {
        throw const FormatException(
          'No available or unique shoreline locations',
        );
      }

      if (!mounted || requestNumber != _requestNumber) return;

      final chosen = sites.firstWhere(
        (site) => site.id == _siteId,
        orElse: () => sites.first,
      );

      final desiredYear =
          _requestedYear ?? (_sites.isEmpty ? chosen.firstYear : _forecastYear);

      final year = desiredYear.clamp(chosen.firstYear, chosen.lastYear).toInt();

      setState(() {
        _sites = sites;
      });

      await _loadPrediction(site: chosen, year: year);
    } catch (error) {
      debugPrint('Shoreline location error: $error');

      if (!mounted || requestNumber != _requestNumber) return;

      setState(() {
        _error =
            'Unable to load available forecasts. '
            'Check the backend connection and model files.';
        _loading = false;
      });
    }
  }

  // LOAD FORECAST FOR THE SELECTED LOCATION

  Future<void> _loadPrediction({
    required _ForecastSite site,
    required int year,
  }) async {
    final requestNumber = ++_requestNumber;

    setState(() {
      _siteId = site.id;
      _site = site.name;
      _referenceYear = site.referenceYear;
      _requestedYear = year;

      _loading = true;
      _mapReady = false;
      _error = null;
      _qualityWarning = '';
      _evaluation = null;
      _transects = [];
    });

    try {
      final uri = Uri.parse('${widget.baseUrl}/shoreline-prediction')
          .replace(queryParameters: {'site': site.id, 'year': '$year'});

      final response = await http.get(uri).timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}');
      }

      final body = jsonDecode(response.body) as Map<String, dynamic>;

      final referenceYear = (body['reference_year'] as num).toInt();

      final forecastYear = (body['forecast_year'] as num).toInt();

      final records = (body['transects'] as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();

      records.sort(
        (a, b) => (a['transect_id'] as num).compareTo(b['transect_id'] as num),
      );

      if (body['site_id'] != site.id ||
          body['site'] != site.name ||
          referenceYear != site.referenceYear ||
          forecastYear != year ||
          year < site.firstYear ||
          year > site.lastYear ||
          records.length != site.transectCount ||
          (body['transect_count'] as num).toInt() != site.transectCount) {
        throw const FormatException(
          'Forecast does not match the selected location/year',
        );
      }

      final ids = <int>{};

      for (final row in records) {
        final id = row['transect_id'] as num;

        if (!id.isFinite ||
            id != id.toInt() ||
            id < 1 ||
            !ids.add(id.toInt())) {
          throw const FormatException('Invalid or duplicate transect');
        }

        _mapPoint(row, 'reference_point');
        _mapPoint(row, 'predicted_point');

        for (final field in [
          'reference_position_m',
          'predicted_position_m',
          'change_from_reference_m',
        ]) {
          if (!(row[field] as num).isFinite) {
            throw const FormatException('Invalid position');
          }
        }
      }

      if (!mounted || requestNumber != _requestNumber) return;

      setState(() {
        _forecastYear = forecastYear;
        _referenceYear = referenceYear;
        _transects = records;
        _qualityWarning = body['quality_warning']?.toString() ?? '';
        _qcStatus = body['qc_status']?.toString() ?? 'UNVALIDATED';
        _evaluation = body['evaluation'] is Map
            ? Map<String, dynamic>.from(body['evaluation'] as Map)
            : null;
      });
    } catch (error) {
      debugPrint('Shoreline prediction error: $error');

      if (!mounted || requestNumber != _requestNumber) return;

      setState(() {
        _error =
            'Unable to load the forecast for ${site.name}. '
            'Check your connection or try another year.';
      });
    } finally {
      if (mounted && requestNumber == _requestNumber) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  bool get _belowBaseline =>
      _evaluation?['lr_worse_than_baseline'] == true;

  Widget _modelNotes() {
    final scores = _evaluation?['scores'];
    final lr = scores is Map ? scores['LinearRegression'] : null;
    final baseline = scores is Map ? scores['NoChangeBaseline'] : null;

    final lrMae = lr is Map ? lr['MAE_m'] : null;
    final baselineMae = baseline is Map ? baseline['MAE_m'] : null;

    final evaluationName = _evaluation?['name']?.toString().replaceAll(
      '_',
      ' ',
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Experimental · $_qcStatus',
          style: const TextStyle(color: _muted, fontSize: 12),
        ),
        if (_qualityWarning.isNotEmpty) ...[
          const SizedBox(height: 10),
          _notice(_qualityWarning, warning: true),
        ],
        if (lrMae is num && baselineMae is num) ...[
          const SizedBox(height: 12),
          Text(
            evaluationName ?? 'Holdout evaluation',
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          _measurement(
            'Linear Regression MAE',
            '${lrMae.toStringAsFixed(2)} m',
          ),
          _measurement(
            'No-change baseline MAE',
            '${baselineMae.toStringAsFixed(2)} m',
          ),
          const Text(
            'Lower MAE means lower average error in this test. '
            'These results do not establish accuracy for every '
            'forecast year.',
            style: TextStyle(color: _muted, fontSize: 12, height: 1.5),
          ),
        ],
      ],
    );
  }

  // MAP HELPERS

  LatLng _mapPoint(Map<String, dynamic> row, String field) {
    final point = row[field] as Map;
    final latitude = (point['latitude'] as num).toDouble();
    final longitude = (point['longitude'] as num).toDouble();

    if (!latitude.isFinite ||
        !longitude.isFinite ||
        latitude.abs() > 90 ||
        longitude.abs() > 180) {
      throw const FormatException('Invalid map coordinate');
    }

    return LatLng(latitude, longitude);
  }

  List<LatLng> get _allPoints => [
    for (final row in _transects) ...[
      _mapPoint(row, 'reference_point'),
      _mapPoint(row, 'predicted_point'),
    ],
  ];

  int get _outsideCount => _transects.where((row) {
    return (row['predicted_point'] as Map)['outside_transect'] == true;
  }).length;

  String _signed(num value) {
    return '${value > 0 ? '+' : ''}${value.toStringAsFixed(2)} m';
  }

  void _fitMap() {
    if (!_mapReady || _transects.isEmpty) return;

    _mapController.fitCamera(
      CameraFit.bounds(
        bounds: LatLngBounds.fromPoints(_allPoints),
        padding: const EdgeInsets.all(48),
        maxZoom: 17,
      ),
    );
  }

  void _zoom(double delta) {
    if (!_mapReady) return;

    final camera = _mapController.camera;

    _mapController.move(
      camera.center,
      (camera.zoom + delta).clamp(5.0, 19.0).toDouble(),
    );
  }

  // LOCATION AND YEAR PANEL

  Future<void> _showSelection() async {
    if (_sites.isEmpty) return;

    var selectedSite = _sites.firstWhere(
      (site) => site.id == _siteId,
      orElse: () => _sites.first,
    );

    var selectedYear = (_requestedYear ?? _forecastYear)
        .clamp(selectedSite.firstYear, selectedSite.lastYear)
        .toInt();

    final selection = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: _panel,
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, updateSheet) {
            return ConstrainedBox(
              constraints: BoxConstraints(
                maxHeight: MediaQuery.sizeOf(context).height * 0.85,
              ),
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Choose your forecast',
                      style: TextStyle(
                        fontSize: 23,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Select a location and a year to compare '
                      'with the reference shoreline.',
                      style: TextStyle(color: _muted, height: 1.5),
                    ),
                    const SizedBox(height: 22),
                    DropdownButtonFormField<String>(
                      initialValue: selectedSite.id,
                      isExpanded: true,
                      decoration: const InputDecoration(
                        labelText: 'Location',
                        border: OutlineInputBorder(),
                      ),
                      items: _sites.map((site) {
                        return DropdownMenuItem<String>(
                          value: site.id,
                          child: Text(site.name),
                        );
                      }).toList(),
                      onChanged: (value) {
                        if (value == null) return;

                        updateSheet(() {
                          selectedSite = _sites.firstWhere(
                            (site) => site.id == value,
                          );

                          selectedYear = selectedYear
                              .clamp(
                                selectedSite.firstYear,
                                selectedSite.lastYear,
                              )
                              .toInt();
                        });
                      },
                    ),
                    const SizedBox(height: 10),
                    Text(
                      '${selectedSite.transectCount} transects · '
                      'Reference ${selectedSite.referenceYear}',
                      style: const TextStyle(color: _muted, fontSize: 12),
                    ),
                    const SizedBox(height: 20),
                    DropdownButtonFormField<int>(
                      key: ValueKey(selectedSite.id),
                      initialValue: selectedYear,
                      isExpanded: true,
                      decoration: const InputDecoration(
                        labelText: 'Forecast year',
                        border: OutlineInputBorder(),
                      ),
                      items: List.generate(
                        selectedSite.lastYear - selectedSite.firstYear + 1,
                        (i) {
                          final year = selectedSite.firstYear + i;
                          final horizon = year - selectedSite.referenceYear;

                          return DropdownMenuItem<int>(
                            value: year,
                            child: Text(
                              '$year (+$horizon '
                              '${horizon == 1 ? 'year' : 'years'})',
                            ),
                          );
                        },
                      ),
                      onChanged: (value) {
                        if (value != null) {
                          updateSheet(() {
                            selectedYear = value;
                          });
                        }
                      },
                    ),
                    const SizedBox(height: 16),
                    _notice(
                      'Reference: ${selectedSite.referenceYear}. '
                      'This is the dataset baseline, '
                      'not a live shoreline.',
                    ),
                    if (selectedSite.qualityWarning.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      _notice(selectedSite.qualityWarning, warning: true),
                    ],
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: () {
                          Navigator.pop(sheetContext, {
                            'site_id': selectedSite.id,
                            'year': selectedYear,
                          });
                        },
                        icon: const Icon(Icons.travel_explore_rounded),
                        label: const Text('Show forecast on map'),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );

    if (!mounted || selection == null) return;

    final site = _sites.firstWhere((site) => site.id == selection['site_id']);

    final year = selection['year'] as int;

    if (_transects.isNotEmpty && site.id == _siteId && year == _forecastYear) {
      return;
    }

    await _loadPrediction(site: site, year: year);
  }

  // LINE APPEARANCE

  Widget _palette(
    String title,
    Map<String, Color> colors,
    Color selected,
    ValueChanged<Color> update,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(height: 10),
        Wrap(
          spacing: 12,
          runSpacing: 10,
          children: [
            for (final entry in colors.entries)
              Tooltip(
                message: entry.key,
                child: Semantics(
                  button: true,
                  selected: entry.value == selected,
                  label: entry.key,
                  child: Material(
                    color: entry.value,
                    shape: CircleBorder(
                      side: BorderSide(
                        color: entry.value == selected
                            ? Colors.white
                            : Colors.transparent,
                        width: 3,
                      ),
                    ),
                    child: InkWell(
                      customBorder: const CircleBorder(),
                      onTap: () => update(entry.value),
                      child: SizedBox(
                        width: 44,
                        height: 44,
                        child: entry.value == selected
                            ? const Icon(
                                Icons.check_rounded,
                                color: Color(0xFF0B1425),
                              )
                            : null,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }

  Future<void> _showAppearance() async {
    var referenceColor = _referenceColor;
    var predictionColor = _predictionColor;
    var showReference = _showReference;
    var showPrediction = _showPrediction;
    var dashed = _dashedPrediction;
    var width = _lineWidth;

    final applied = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: _panel,
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, updateSheet) {
            return ConstrainedBox(
              constraints: BoxConstraints(
                maxHeight: MediaQuery.sizeOf(context).height * 0.85,
              ),
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Shoreline appearance',
                      style: TextStyle(
                        fontSize: 23,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Change the map display to make '
                      'the comparison easier to read.',
                      style: TextStyle(color: _muted, height: 1.5),
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text('$_referenceYear reference'),
                      value: showReference,
                      onChanged: (value) {
                        updateSheet(() {
                          showReference = value;
                        });
                      },
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text('$_forecastYear prediction'),
                      value: showPrediction,
                      onChanged: (value) {
                        updateSheet(() {
                          showPrediction = value;
                        });
                      },
                    ),
                    if (!showReference && !showPrediction)
                      _notice(
                        'Keep at least one shoreline visible.',
                        warning: true,
                      ),
                    const Divider(height: 28),
                    _palette(
                      'Reference color',
                      _referenceColors,
                      referenceColor,
                      (value) {
                        updateSheet(() {
                          referenceColor = value;
                        });
                      },
                    ),
                    const SizedBox(height: 20),
                    _palette(
                      'Prediction color',
                      _predictionColors,
                      predictionColor,
                      (value) {
                        updateSheet(() {
                          predictionColor = value;
                        });
                      },
                    ),
                    const SizedBox(height: 16),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Dashed prediction line'),
                      subtitle: const Text(
                        'Helps distinguish the forecast '
                        'from the reference',
                      ),
                      value: dashed,
                      onChanged: (value) {
                        updateSheet(() {
                          dashed = value;
                        });
                      },
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Line thickness',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                    Slider(
                      value: width,
                      min: 2,
                      max: 7,
                      divisions: 5,
                      label: width.toStringAsFixed(0),
                      onChanged: (value) {
                        updateSheet(() {
                          width = value;
                        });
                      },
                    ),
                    TextButton.icon(
                      onPressed: () {
                        updateSheet(() {
                          referenceColor = _referenceColors['Blue']!;
                          predictionColor = _predictionColors['Orange']!;
                          showReference = true;
                          showPrediction = true;
                          dashed = true;
                          width = 4;
                        });
                      },
                      icon: const Icon(Icons.restart_alt_rounded),
                      label: const Text('Reset appearance'),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: !showReference && !showPrediction
                            ? null
                            : () => Navigator.pop(sheetContext, true),
                        child: const Text('Apply appearance'),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );

    if (!mounted || applied != true) return;

    setState(() {
      _referenceColor = referenceColor;
      _predictionColor = predictionColor;
      _showReference = showReference;
      _showPrediction = showPrediction;
      _dashedPrediction = dashed;
      _lineWidth = width;
    });
  }

  // INFORMATION PANELS

  Widget _notice(String text, {bool warning = false}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: (warning ? const Color(0xFFF59E0B) : _accent).withValues(
          alpha: 0.08,
        ),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: warning ? const Color(0xFFFACC15) : _muted,
          fontSize: 12,
          height: 1.5,
        ),
      ),
    );
  }

  Widget _measurement(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 9),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: _muted, fontSize: 12)),
          const SizedBox(height: 4),
          Text(
            value,
            style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }

  void _showInfoSheet(Widget content) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: _panel,
      builder: (context) {
        return ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.sizeOf(context).height * 0.82,
          ),
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
            child: content,
          ),
        );
      },
    );
  }

  void _showDetails(Map<String, dynamic> row) {
    final outside = (row['predicted_point'] as Map)['outside_transect'] == true;

    _showInfoSheet(
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '$_site · Transect ${row['transect_id']}',
            style: const TextStyle(fontSize: 23, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text(
            'Experimental shoreline comparison',
            style: TextStyle(color: _muted),
          ),
          const SizedBox(height: 18),
          _measurement(
            '$_referenceYear reference position',
            '${(row['reference_position_m'] as num).toStringAsFixed(2)} m',
          ),
          _measurement(
            '$_forecastYear predicted position',
            '${(row['predicted_position_m'] as num).toStringAsFixed(2)} m',
          ),
          _measurement(
            'Change along transect',
            _signed(row['change_from_reference_m'] as num),
          ),
          const SizedBox(height: 12),
          _notice(
            'Positions are measured from this transect’s origin. '
            'Negative change means movement toward the origin; '
            'positive change means movement away from it.',
          ),
          if (outside) ...[
            const SizedBox(height: 12),
            _notice(
              'This prediction extends beyond the surveyed transect.',
              warning: true,
            ),
          ],
        ],
      ),
    );
  }

  void _showSummary() {
    _showInfoSheet(
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'Shoreline comparison',
            style: TextStyle(fontSize: 23, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(
            '$_site · $_referenceYear → $_forecastYear',
            style: const TextStyle(color: _muted),
          ),
          const SizedBox(height: 16),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              horizontalMargin: 8,
              columnSpacing: 20,
              columns: [
                const DataColumn(label: Text('Transect')),
                DataColumn(numeric: true, label: Text('$_referenceYear\n(m)')),
                DataColumn(numeric: true, label: Text('$_forecastYear\n(m)')),
                const DataColumn(numeric: true, label: Text('Change\n(m)')),
              ],
              rows: _transects.map((row) {
                final outside =
                    (row['predicted_point'] as Map)['outside_transect'] == true;

                final change = row['change_from_reference_m'] as num;

                return DataRow(
                  cells: [
                    DataCell(Text('T${row['transect_id']}')),
                    DataCell(
                      Text(
                        (row['reference_position_m'] as num).toStringAsFixed(2),
                      ),
                    ),
                    DataCell(
                      Text(
                        '${(row['predicted_position_m'] as num).toStringAsFixed(2)}'
                        '${outside ? ' *' : ''}',
                      ),
                    ),
                    DataCell(
                      Text(
                        '${change > 0 ? '+' : ''}'
                        '${change.toStringAsFixed(2)}',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ],
                );
              }).toList(),
            ),
          ),
          const SizedBox(height: 18),
          _notice(
            'Change = predicted position − reference position. '
            'Negative values indicate movement toward the transect '
            'origin. Lines connect the transect points to '
            'approximate the shoreline.',
          ),
          if (_outsideCount > 0) ...[
            const SizedBox(height: 12),
            _notice(
              '* Prediction extends beyond the surveyed transect.',
              warning: true,
            ),
          ],
          const SizedBox(height: 12),
          const Text(
            'Experimental Linear Regression forecast. '
            'The reference year is a dataset baseline, '
            'not a live shoreline.',
            style: TextStyle(color: _muted, fontSize: 12, height: 1.5),
          ),
          const SizedBox(height: 14),
          _modelNotes(),
        ],
      ),
    );
  }

  // MAP SYMBOLS AND LINES

  Marker _marker(Map<String, dynamic> row, {required bool predicted}) {
    return Marker(
      point: _mapPoint(row, predicted ? 'predicted_point' : 'reference_point'),
      width: 40,
      height: 40,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => _showDetails(row),
        child: Center(
          child: Icon(
            predicted ? Icons.diamond_rounded : Icons.add_box_rounded,
            color: predicted ? _predictionColor : _referenceColor,
            size: 25,
            shadows: const [Shadow(color: Colors.black, blurRadius: 4)],
          ),
        ),
      ),
    );
  }

  Polyline _line(List<LatLng> points, Color color, {bool dashed = false}) {
    if (dashed) {
      return Polyline(
        points: points,
        color: color,
        strokeWidth: _lineWidth,
        borderColor: Colors.black,
        borderStrokeWidth: 0.7,
        pattern: StrokePattern.dashed(segments: [12, 8]),
      );
    }

    return Polyline(
      points: points,
      color: color,
      strokeWidth: _lineWidth,
      borderColor: Colors.black,
      borderStrokeWidth: 0.7,
    );
  }

  Widget _layerChip({required bool reference}) {
    final shown = reference ? _showReference : _showPrediction;
    final color = reference ? _referenceColor : _predictionColor;

    return FilterChip(
      label: Text(
        reference ? '$_referenceYear reference' : '$_forecastYear prediction',
      ),
      avatar: Icon(
        reference ? Icons.horizontal_rule_rounded : Icons.more_horiz_rounded,
        color: color,
        size: 22,
      ),
      selected: shown,
      showCheckmark: false,
      backgroundColor: _panel,
      selectedColor: color.withValues(alpha: 0.15),
      side: BorderSide(color: shown ? color : _border),
      labelStyle: TextStyle(
        color: shown ? const Color(0xFFF0F5FA) : _muted,
        fontSize: 12,
      ),
      onSelected: (value) {
        final otherVisible = reference ? _showPrediction : _showReference;

        if (!value && !otherVisible) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Keep at least one shoreline visible.'),
            ),
          );
          return;
        }

        setState(() {
          if (reference) {
            _showReference = value;
          } else {
            _showPrediction = value;
          }
        });
      },
    );
  }

  Widget _mapButton(IconData icon, String tooltip, VoidCallback action) {
    return Material(
      color: _panel,
      elevation: 3,
      borderRadius: BorderRadius.circular(14),
      child: IconButton(
        tooltip: tooltip,
        onPressed: action,
        icon: Icon(icon, color: const Color(0xFFF0F5FA)),
      ),
    );
  }

  Widget _buildMap() {
    if (_loading) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Preparing shoreline comparison…'),
          ],
        ),
      );
    }

    if (_error != null) {
      return Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.wifi_off_rounded, size: 44, color: _muted),
              const SizedBox(height: 14),
              Text(
                _error!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: _muted, height: 1.5),
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _loadSitesAndPrediction,
                icon: const Icon(Icons.refresh_rounded),
                label: const Text('Try again'),
              ),
            ],
          ),
        ),
      );
    }

    final reference = _transects
        .map((row) => _mapPoint(row, 'reference_point'))
        .toList();

    final prediction = _transects
        .map((row) => _mapPoint(row, 'predicted_point'))
        .toList();

    return ClipRRect(
      borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      child: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCameraFit: CameraFit.bounds(
                bounds: LatLngBounds.fromPoints(_allPoints),
                padding: const EdgeInsets.all(48),
                maxZoom: 17,
              ),
              minZoom: 5,
              maxZoom: 19,
              onMapReady: () {
                _mapReady = true;
              },
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
                    if (_showReference) _line(reference, _referenceColor),
                    if (_showPrediction)
                      _line(
                        prediction,
                        _predictionColor,
                        dashed: _dashedPrediction,
                      ),
                  ],
                ),
              ),
              MarkerLayer(
                markers: [
                  for (final row in _transects) ...[
                    if (_showReference) _marker(row, predicted: false),
                    if (_showPrediction) _marker(row, predicted: true),
                  ],
                ],
              ),
              SimpleAttributionWidget(
                source: const Text(
                  'OpenStreetMap contributors',
                  style: TextStyle(color: Color(0xFF152238), fontSize: 10),
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
          Positioned(
            top: 16,
            right: 12,
            child: Column(
              children: [
                _mapButton(Icons.add_rounded, 'Zoom in', () => _zoom(1)),
                const SizedBox(height: 8),
                _mapButton(Icons.remove_rounded, 'Zoom out', () => _zoom(-1)),
                const SizedBox(height: 8),
                _mapButton(
                  Icons.fit_screen_rounded,
                  'Show both shorelines',
                  _fitMap,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // MAIN SCREEN

  @override
  Widget build(BuildContext context) {
    final ready = !_loading && _error == null && _transects.isNotEmpty;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Shoreline Prediction'),
        actions: [
          IconButton(
            tooltip: 'Shoreline appearance',
            onPressed: ready ? _showAppearance : null,
            icon: const Icon(Icons.tune_rounded),
          ),
          IconButton(
            tooltip: 'Refresh forecast',
            onPressed: _loading ? null : _loadSitesAndPrediction,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: Material(
                color: _panel,
                borderRadius: BorderRadius.circular(18),
                child: InkWell(
                  borderRadius: BorderRadius.circular(18),
                  onTap: _loading || _sites.isEmpty ? null : _showSelection,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.travel_explore_rounded,
                          color: _accent,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'LOCATION & YEAR',
                                style: TextStyle(
                                  color: _accent,
                                  fontSize: 10,
                                  letterSpacing: 1.3,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 5),
                              Text(
                                _loading
                                    ? 'Loading forecast…'
                                    : _sites.isNotEmpty
                                    ? '$_site · ${_requestedYear ?? _forecastYear}'
                                    : 'Forecast unavailable',
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 4),
                              const Text(
                                'Tap to choose your forecast',
                                style: TextStyle(color: _muted, fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                        const Icon(Icons.expand_more_rounded, color: _accent),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            if (ready)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 2,
                  children: [
                    _layerChip(reference: true),
                    _layerChip(reference: false),
                  ],
                ),
              ),
            const SizedBox(height: 8),
            Expanded(child: _buildMap()),
            if (ready)
              ConstrainedBox(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.sizeOf(context).height * 0.30,
                ),
                child: SingleChildScrollView(
                  child: Container(
                    margin: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: _panel,
                      borderRadius: BorderRadius.circular(22),
                      border: Border.all(color: _border),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '$_referenceYear → $_forecastYear',
                          style: const TextStyle(
                            fontSize: 21,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          '${_transects.length} transects · '
                          '${_forecastYear - _referenceYear} years '
                          'from reference',
                          style: const TextStyle(color: _muted, fontSize: 12),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Experimental · $_qcStatus',
                          style: const TextStyle(
                            color: _muted,
                            fontSize: 12,
                            height: 1.5,
                          ),
                        ),
                        if (_belowBaseline)
                          const Padding(
                            padding: EdgeInsets.only(top: 6),
                            child: Text(
                              'LR performed worse than the no-change '
                              'baseline in the holdout test.',
                              style: TextStyle(
                                color: Color(0xFFFACC15),
                                fontSize: 12,
                                height: 1.5,
                              ),
                            ),
                          ),
                        if (_outsideCount > 0)
                          Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Text(
                              '$_outsideCount of ${_transects.length} '
                              'predictions extend beyond the '
                              'surveyed transects.',
                              style: const TextStyle(
                                color: Color(0xFFFACC15),
                                fontSize: 12,
                              ),
                            ),
                          ),
                        const SizedBox(height: 12),
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton.icon(
                            onPressed: _showSummary,
                            icon: const Icon(Icons.table_chart_outlined),
                            label: const Text('View comparison details'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
