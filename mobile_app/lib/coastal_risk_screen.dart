import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

const _accent = Color(0xFF36D6BE);
const _panel = Color(0xFF152238);
const _muted = Color(0xFFA8B8CC);
const _border = Color(0xFF29384D);

// SHARED DISPLAY HELPERS

String _placeName(Map<String, dynamic> point) {
  final name = point['location']?.toString().trim() ?? '';

  return name.isEmpty ? 'Unnamed coastal location' : name;
}

String _placeSubtitle(Map<String, dynamic> point) {
  return [
    point['district'],
    point['coastal_cell'],
  ]
      .where((value) => value != null && '$value'.trim().isNotEmpty)
      .join(' • ');
}

String _measurement(dynamic value, String unit) {
  if (value is num) {
    return '${value.toStringAsFixed(2)} $unit';
  }

  return 'Not available';
}

String _sourceName(dynamic value) {
  switch (value) {
    case 'JPS_Original':
      return 'Original JPS location';

    case 'Interpolated':
      return 'Estimated between JPS locations';

    case 'JPS_Reported':
      return 'JPS reported rate';

    case 'Spatial_Interpolation':
      return 'Spatial interpolation';

    default:
      return value == null
          ? 'Not available'
          : '$value'.replaceAll('_', ' ');
  }
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
      return Icons.check_circle_outline_rounded;

    case 'Warning':
      return Icons.warning_amber_rounded;

    case 'Critical':
      return Icons.priority_high_rounded;

    case 'Protected':
      return Icons.shield_outlined;

    default:
      return Icons.location_on_outlined;
  }
}

class _RiskBadge extends StatelessWidget {
  final String risk;

  const _RiskBadge(this.risk);

  @override
  Widget build(BuildContext context) {
    final color = _riskColor(risk);

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: 10,
        vertical: 7,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.13),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: color.withValues(alpha: 0.4),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            _riskIcon(risk),
            color: color,
            size: 16,
          ),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              risk,
              style: TextStyle(
                color: color,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

Widget _detailRow(String label, String value) {
  return Padding(
    padding: const EdgeInsets.symmetric(vertical: 9),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: _muted,
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    ),
  );
}

Widget _section(String title, List<Widget> children) {
  return Container(
    margin: const EdgeInsets.only(bottom: 16),
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: _panel,
      borderRadius: BorderRadius.circular(22),
      border: Border.all(color: _border),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 12),
        ...children,
      ],
    ),
  );
}

// COASTAL RISK MAP

class CoastalRiskMapScreen extends StatefulWidget {
  final String baseUrl;

  const CoastalRiskMapScreen({
    super.key,
    required this.baseUrl,
  });

  @override
  State<CoastalRiskMapScreen> createState() =>
      _CoastalRiskMapScreenState();
}

class _CoastalRiskMapScreenState
    extends State<CoastalRiskMapScreen> {
  final MapController _mapController = MapController();

  List<Map<String, dynamic>> _points = [];
  List<Polyline> _riskLines = [];

  Map<String, dynamic>? _selectedPlace;

  bool _loading = true;
  bool _mapReady = false;
  bool _includeInterpolated = false;
  bool _showRiskLines = true;

  String? _error;

  @override
  void initState() {
    super.initState();
    _loadLocations();
  }

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  LatLng _coordinates(Map<String, dynamic> point) {
    return LatLng(
      (point['latitude'] as num).toDouble(),
      (point['longitude'] as num).toDouble(),
    );
  }

  List<Map<String, dynamic>> get _searchPlaces {
    // Search original survey locations so interpolated points
    // do not repeat the same place name hundreds of times.
    final original = _points
        .where((point) => point['source_type'] == 'JPS_Original')
        .toList();

    final places = original.isEmpty
        ? List<Map<String, dynamic>>.from(_points)
        : original;

    places.sort((a, b) {
      final nameOrder = _placeName(a)
          .toLowerCase()
          .compareTo(_placeName(b).toLowerCase());

      return nameOrder != 0
          ? nameOrder
          : _placeSubtitle(a).compareTo(_placeSubtitle(b));
    });

    return places;
  }

  Future<void> _loadLocations() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final response = await http
          .get(Uri.parse('${widget.baseUrl}/locations'))
          .timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) {
        throw Exception(
          'Server returned HTTP ${response.statusCode}.',
        );
      }

      final body =
          jsonDecode(response.body) as Map<String, dynamic>;

      final loaded = (body['locations'] as List)
          .map(
            (item) => Map<String, dynamic>.from(item as Map),
          )
          .toList();

      if (!mounted) return;

      final selectedId = _selectedPlace?['transect_id'];

      Map<String, dynamic>? refreshedSelection;

      for (final point in loaded) {
        if (point['transect_id'] == selectedId) {
          refreshedSelection = point;
          break;
        }
      }

      setState(() {
        _points = loaded;
        _selectedPlace = refreshedSelection;
        _riskLines = _createRiskLines();
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        _error =
            'Could not load coastal locations. '
            'Check the connection and retry.';
      });
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<void> _openSearch() async {
    if (_loading || _points.isEmpty) return;

    final selected =
        await showSearch<Map<String, dynamic>?>(
          context: context,
          delegate: _PlaceSearchDelegate(_searchPlaces),
        );

    if (!mounted || selected == null) return;

    _selectPlace(selected);
  }

  void _selectPlace(Map<String, dynamic> point) {
    FocusScope.of(context).unfocus();

    setState(() {
      _selectedPlace = point;
    });

    _focusSelectedPlace();
  }

  void _focusSelectedPlace() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          !_mapReady ||
          _selectedPlace == null) {
        return;
      }

      _mapController.move(
        _coordinates(_selectedPlace!),
        15,
      );
    });
  }

  void _zoom(double delta) {
    if (!_mapReady) return;

    final camera = _mapController.camera;

    _mapController.move(
      camera.center,
      (camera.zoom + delta)
          .clamp(5.0, 19.0)
          .toDouble(),
    );
  }

  void _resetView() {
    setState(() {
      _selectedPlace = null;
    });

    if (_mapReady) {
      _mapController.move(
        const LatLng(5.10, 103.15),
        8,
      );
    }
  }

  List<Marker> _createMarkers() {
    final selectedId = _selectedPlace?['transect_id'];

    final visible = _points.where(
      (point) =>
          (_includeInterpolated ||
              point['source_type'] == 'JPS_Original') &&
          point['transect_id'] != selectedId,
    );

    return visible.map((point) {
      final risk = '${point['risk_label']}';

      return Marker(
        point: _coordinates(point),
        width: 32,
        height: 32,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => _selectPlace(point),
          child: Icon(
            _riskIcon(risk),
            color: _riskColor(risk),
            size: 24,
            shadows: const [
              Shadow(
                color: Colors.black,
                blurRadius: 3,
              ),
            ],
          ),
        ),
      );
    }).toList();
  }

  List<Polyline> _createRiskLines() {
    final ordered =
        List<Map<String, dynamic>>.from(_points)
          ..sort(
            (a, b) => (a['transect_id'] as num)
                .compareTo(b['transect_id'] as num),
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

      final from = _coordinates(previous);
      final to = _coordinates(current);

      final risk = '${previous['risk_label']}';

      final consecutiveIds =
          (current['transect_id'] as num) -
                  (previous['transect_id'] as num) ==
              1;

      final sameCell =
          previous['coastal_cell'] ==
          current['coastal_cell'];

      final sameRisk =
          previous['risk_label'] ==
          current['risk_label'];

      final hasRiskCategory = [
        'Stable',
        'Warning',
        'Critical',
      ].contains(risk);

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

  Future<void> _showFilters() async {
    var includeInterpolated = _includeInterpolated;
    var showRiskLines = _showRiskLines;

    final applied = await showModalBottomSheet<bool>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      backgroundColor: _panel,
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return SafeArea(
              child: SingleChildScrollView(
                padding:
                    const EdgeInsets.fromLTRB(
                      12,
                      0,
                      12,
                      20,
                    ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    const Padding(
                      padding: EdgeInsets.all(12),
                      child: Text(
                        'Map layers',
                        style: TextStyle(
                          fontSize: 21,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    SwitchListTile(
                      title: const Text(
                        'Estimated points',
                      ),
                      subtitle: const Text(
                        'Show interpolated locations '
                        'between JPS surveys',
                      ),
                      value: includeInterpolated,
                      onChanged: (value) {
                        setSheetState(() {
                          includeInterpolated = value;
                        });
                      },
                    ),
                    SwitchListTile(
                      title: const Text(
                        'Estimated risk lines',
                      ),
                      subtitle: const Text(
                        'Connect nearby points with '
                        'the same risk category',
                      ),
                      value: showRiskLines,
                      onChanged: (value) {
                        setSheetState(() {
                          showRiskLines = value;
                        });
                      },
                    ),
                    const SizedBox(height: 12),
                    Padding(
                      padding:
                          const EdgeInsets.symmetric(
                            horizontal: 12,
                          ),
                      child: SizedBox(
                        width: double.infinity,
                        child: FilledButton(
                          onPressed: () {
                            Navigator.pop(
                              sheetContext,
                              true,
                            );
                          },
                          child: const Text(
                            'Apply layers',
                          ),
                        ),
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
      _includeInterpolated = includeInterpolated;
      _showRiskLines = showRiskLines;
    });
  }

  void _showDetails(Map<String, dynamic> point) {
    final risk = '${point['risk_label']}';

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: _panel,
      builder: (sheetContext) {
        return SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(
            24,
            0,
            24,
            24,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment:
                CrossAxisAlignment.start,
            children: [
              const Text(
                'PLACE DETAILS',
                style: TextStyle(
                  color: _accent,
                  fontSize: 11,
                  letterSpacing: 1.8,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                _placeName(point),
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _placeSubtitle(point),
                style: const TextStyle(
                  color: _muted,
                ),
              ),
              const SizedBox(height: 18),
              _RiskBadge(risk),
              const SizedBox(height: 12),
              _detailRow(
                'Annual erosion rate',
                _measurement(
                  point['primary_rate_m_yr'],
                  'm/year',
                ),
              ),
              _detailRow(
                'Location source',
                _sourceName(point['source_type']),
              ),
              _detailRow(
                'Rate source',
                _sourceName(
                  point['projection_source'],
                ),
              ),
              const Divider(height: 28),
              const Text(
                'Risk categories describe the project '
                'dataset, not live coastal conditions. '
                'Interpolated points are estimates '
                'between JPS locations.',
                style: TextStyle(
                  color: _muted,
                  fontSize: 12,
                  height: 1.6,
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: () {
                    final navigator =
                        Navigator.of(sheetContext);

                    navigator.pop();

                    navigator.push(
                      MaterialPageRoute(
                        builder: (_) {
                          return RiskAssessmentScreen(
                            baseUrl: widget.baseUrl,
                            place: point,
                          );
                        },
                      ),
                    );
                  },
                  icon: const Icon(
                    Icons.timeline_rounded,
                  ),
                  label: const Text(
                    'View estimated retreat',
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _selectedCard(Map<String, dynamic> point) {
    return Container(
      margin: const EdgeInsets.fromLTRB(
        16,
        12,
        16,
        12,
      ),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _panel,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: _accent.withValues(alpha: 0.45),
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment:
                CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.only(top: 2),
                child: Icon(
                  Icons.place_rounded,
                  color: _accent,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    Text(
                      _placeName(point),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      _placeSubtitle(point),
                      style: const TextStyle(
                        color: _muted,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Clear selected location',
                visualDensity:
                    VisualDensity.compact,
                onPressed: () {
                  setState(() {
                    _selectedPlace = null;
                  });
                },
                icon: const Icon(
                  Icons.close_rounded,
                  size: 19,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment:
                WrapCrossAlignment.center,
            children: [
              _RiskBadge('${point['risk_label']}'),
              Text(
                _measurement(
                  point['primary_rate_m_yr'],
                  'm/year',
                ),
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (point['source_type'] ==
                  'Interpolated')
                const Text(
                  'Estimated location',
                  style: TextStyle(
                    color: _muted,
                    fontSize: 12,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => _showDetails(point),
              icon: const Icon(
                Icons.info_outline_rounded,
                size: 19,
              ),
              label: const Text(
                'View place details',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _mapButton(
    IconData icon,
    String tooltip,
    VoidCallback action,
  ) {
    return Material(
      color: _panel,
      elevation: 3,
      borderRadius: BorderRadius.circular(14),
      child: IconButton(
        tooltip: tooltip,
        onPressed: action,
        icon: Icon(
          icon,
          color: const Color(0xFFF0F5FA),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final selected = _selectedPlace;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Coastal Risk Map'),
        actions: [
          IconButton(
            tooltip: 'Map layers',
            onPressed: _showFilters,
            icon: const Icon(
              Icons.tune_rounded,
            ),
          ),
          IconButton(
            tooltip: 'Refresh locations',
            onPressed:
                _loading ? null : _loadLocations,
            icon: const Icon(
              Icons.refresh_rounded,
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding:
                  const EdgeInsets.fromLTRB(
                    16,
                    4,
                    16,
                    12,
                  ),
              child: Material(
                color: _panel,
                borderRadius:
                    BorderRadius.circular(18),
                child: InkWell(
                  borderRadius:
                      BorderRadius.circular(18),
                  onTap:
                      _loading || _points.isEmpty
                      ? null
                      : _openSearch,
                  child: Padding(
                    padding:
                        const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 14,
                        ),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.search_rounded,
                          color: _accent,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            _loading
                                ? 'Loading coastal places…'
                                : 'Search a place or district',
                            style: const TextStyle(
                              color: _muted,
                              fontSize: 14,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        const Icon(
                          Icons.chevron_right_rounded,
                          color: _muted,
                          size: 20,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            SizedBox(
              height: 36,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding:
                    const EdgeInsets.symmetric(
                      horizontal: 16,
                    ),
                children: [
                  for (final risk in [
                    'Stable',
                    'Warning',
                    'Critical',
                    'Protected',
                  ])
                    Padding(
                      padding:
                          const EdgeInsets.only(
                            right: 8,
                          ),
                      child: _RiskBadge(risk),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 10),
            if (_loading)
              const LinearProgressIndicator(
                minHeight: 2,
              ),
            if (_error != null)
              Padding(
                padding:
                    const EdgeInsets.symmetric(
                      horizontal: 16,
                    ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        _error!,
                        style: const TextStyle(
                          color: Color(0xFFFFB4AB),
                          fontSize: 12,
                        ),
                      ),
                    ),
                    TextButton(
                      onPressed:
                          _loading
                          ? null
                          : _loadLocations,
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            Expanded(
              child: ClipRRect(
                borderRadius:
                    const BorderRadius.vertical(
                      top: Radius.circular(24),
                    ),
                child: Stack(
                  children: [
                    FlutterMap(
                      mapController: _mapController,
                      options: MapOptions(
                        initialCenter:
                            const LatLng(
                              5.10,
                              103.15,
                            ),
                        initialZoom: 8,
                        minZoom: 5,
                        maxZoom: 19,
                        onMapReady: () {
                          _mapReady = true;
                          _focusSelectedPlace();
                        },
                      ),
                      children: [
                        TileLayer(
                          urlTemplate:
                              'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                          userAgentPackageName:
                              'my.uitm.izzul.coastal_erosion_fyp',
                          maxNativeZoom: 19,
                        ),
                        if (_showRiskLines)
                          IgnorePointer(
                            child: PolylineLayer(
                              polylines: _riskLines,
                            ),
                          ),
                        MarkerLayer(
                          markers: _createMarkers(),
                        ),
                        if (selected != null)
                          MarkerLayer(
                            markers: [
                              Marker(
                                point:
                                    _coordinates(
                                      selected,
                                    ),
                                width: 52,
                                height: 52,
                                child:
                                    GestureDetector(
                                      onTap: () {
                                        _showDetails(
                                          selected,
                                        );
                                      },
                                      child: Container(
                                        decoration:
                                            BoxDecoration(
                                              color: _riskColor(
                                                '${selected['risk_label']}',
                                              ),
                                              shape:
                                                  BoxShape.circle,
                                              border: Border.all(
                                                color:
                                                    Colors.white,
                                                width: 3,
                                              ),
                                              boxShadow: const [
                                                BoxShadow(
                                                  color:
                                                      Colors.black38,
                                                  blurRadius: 10,
                                                  spreadRadius: 2,
                                                ),
                                              ],
                                            ),
                                        child: Icon(
                                          _riskIcon(
                                            '${selected['risk_label']}',
                                          ),
                                          color:
                                              Colors.white,
                                          size: 28,
                                        ),
                                      ),
                                    ),
                              ),
                            ],
                          ),
                        SimpleAttributionWidget(
                          source: const Text(
                            'OpenStreetMap contributors',
                            style: TextStyle(
                              color:
                                  Color(0xFF152238),
                              fontSize: 11,
                            ),
                          ),
                          backgroundColor:
                              Colors.white,
                          onTap: () {
                            launchUrl(
                              Uri.parse(
                                'https://www.openstreetmap.org/copyright',
                              ),
                              mode:
                                  LaunchMode.externalApplication,
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
                          _mapButton(
                            Icons.add_rounded,
                            'Zoom in',
                            () => _zoom(1),
                          ),
                          const SizedBox(height: 8),
                          _mapButton(
                            Icons.remove_rounded,
                            'Zoom out',
                            () => _zoom(-1),
                          ),
                          const SizedBox(height: 8),
                          _mapButton(
                            Icons.public_rounded,
                            'View Terengganu coastline',
                            _resetView,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            if (selected != null)
              ConstrainedBox(
                constraints: BoxConstraints(
                  maxHeight:
                      MediaQuery.sizeOf(
                        context,
                      ).height *
                      0.34,
                ),
                child: SingleChildScrollView(
                  child: _selectedCard(selected),
                ),
              )
            else
              Padding(
                padding:
                    const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 12,
                    ),
                child: Text(
                  _points.isEmpty && !_loading
                      ? 'No coastal locations loaded. '
                            'Use refresh to try again.'
                      : 'Search a place or tap a marker '
                            'to explore its risk.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: _muted,
                    fontSize: 12,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// SEARCH BY PLACE NAME

class _PlaceSearchDelegate
    extends SearchDelegate<Map<String, dynamic>?> {
  final List<Map<String, dynamic>> places;

  _PlaceSearchDelegate(this.places)
    : super(
        searchFieldLabel: 'Place name or district',
      );

  @override
  List<Widget> buildActions(BuildContext context) {
    return [
      if (query.isNotEmpty)
        IconButton(
          tooltip: 'Clear search',
          icon: const Icon(Icons.close_rounded),
          onPressed: () {
            query = '';
          },
        ),
      IconButton(
        tooltip: 'Search places',
        icon: const Icon(Icons.search_rounded),
        onPressed: () {
          final matches = _matches();

          if (query.trim().isNotEmpty &&
              matches.length == 1) {
            close(context, matches.single);
          } else {
            showResults(context);
          }
        },
      ),
    ];
  }

  @override
  Widget buildLeading(BuildContext context) {
    return IconButton(
      tooltip: 'Back to map',
      icon: const Icon(Icons.arrow_back_rounded),
      onPressed: () => close(context, null),
    );
  }

  List<Map<String, dynamic>> _matches() {
    final terms = query
        .toLowerCase()
        .trim()
        .split(RegExp(r'\s+'))
        .where((term) => term.isNotEmpty)
        .toList();

    return places.where((point) {
      final text =
          '${_placeName(point)} '
                  '${_placeSubtitle(point)}'
              .toLowerCase();

      return terms.every(text.contains);
    }).toList();
  }

  Widget _results(BuildContext context) {
    final matches = _matches();

    if (matches.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.search_off_rounded,
                size: 48,
                color: _muted,
              ),
              const SizedBox(height: 16),
              const Text(
                'No matching coastal place',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Try a shorter place name or its '
                'district. Search covers the project '
                'locations in Terengganu.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: _muted,
                  height: 1.6,
                ),
              ),
            ],
          ),
        ),
      );
    }

    return ListView.builder(
      keyboardDismissBehavior:
          ScrollViewKeyboardDismissBehavior.onDrag,
      padding: const EdgeInsets.fromLTRB(
        16,
        8,
        16,
        24,
      ),
      itemCount: matches.length + 1,
      itemBuilder: (context, index) {
        if (index == 0) {
          return Padding(
            padding:
                const EdgeInsets.symmetric(
                  vertical: 12,
                ),
            child: Text(
              query.trim().isEmpty
                  ? 'JPS SURVEY LOCATIONS'
                  : '${matches.length} matching '
                        'survey locations',
              style: const TextStyle(
                color: _muted,
                fontSize: 12,
                letterSpacing: 0.6,
              ),
            ),
          );
        }

        final point = matches[index - 1];

        return Card(
          color: _panel,
          surfaceTintColor: Colors.transparent,
          margin: const EdgeInsets.only(
            bottom: 10,
          ),
          shape: RoundedRectangleBorder(
            borderRadius:
                BorderRadius.circular(18),
            side: const BorderSide(
              color: _border,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: ListTile(
            contentPadding:
                const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 10,
                ),
            leading: const Icon(
              Icons.place_outlined,
              color: _accent,
            ),
            title: Text(
              _placeName(point),
              style: const TextStyle(
                fontWeight: FontWeight.w600,
              ),
            ),
            subtitle: Padding(
              padding: const EdgeInsets.only(
                top: 8,
              ),
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment.start,
                children: [
                  Text(
                    _placeSubtitle(point),
                    style: const TextStyle(
                      color: _muted,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 8),
                  _RiskBadge(
                    '${point['risk_label']}',
                  ),
                ],
              ),
            ),
            trailing: const Icon(
              Icons.arrow_outward_rounded,
              color: _accent,
              size: 20,
            ),
            onTap: () => close(context, point),
          ),
        );
      },
    );
  }

  @override
  Widget buildResults(BuildContext context) {
    return _results(context);
  }

  @override
  Widget buildSuggestions(BuildContext context) {
    return _results(context);
  }
}

// ASSESSMENT FOR THE SELECTED PLACE

class RiskAssessmentScreen extends StatefulWidget {
  final String baseUrl;
  final Map<String, dynamic> place;

  const RiskAssessmentScreen({
    super.key,
    required this.baseUrl,
    required this.place,
  });

  @override
  State<RiskAssessmentScreen> createState() =>
      _RiskAssessmentScreenState();
}

class _RiskAssessmentScreenState
    extends State<RiskAssessmentScreen> {
  Map<String, dynamic>? _result;

  String? _error;

  bool _loading = false;
  int _years = 10;

  @override
  void initState() {
    super.initState();
    _loadAssessment();
  }

  Future<void> _loadAssessment() async {
    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });

    try {
      // IDs are used internally by the API.
      final uri =
          Uri.parse(
            '${widget.baseUrl}/assessment',
          ).replace(
            queryParameters: {
              'transect_id':
                  '${widget.place['transect_id']}',
              'years': '$_years',
            },
          );

      final response = await http
          .get(uri)
          .timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) {
        throw Exception(
          'Could not load assessment '
          '(HTTP ${response.statusCode}).',
        );
      }

      final body = Map<String, dynamic>.from(
        jsonDecode(response.body) as Map,
      );

      if (!mounted) return;

      setState(() {
        _result = body;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        _error =
            'Could not load the assessment. '
            'Check your connection and try again.';
      });
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Location Assessment',
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            _section(
              'SELECTED PLACE',
              [
                Text(
                  _placeName(widget.place),
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _placeSubtitle(widget.place),
                  style: const TextStyle(
                    color: _muted,
                  ),
                ),
                const SizedBox(height: 16),
                _RiskBadge(
                  '${result?['risk_label'] ?? widget.place['risk_label']}',
                ),
              ],
            ),
            _section(
              'Estimated retreat',
              [
                const Text(
                  'Choose a projection period '
                  'for this location.',
                  style: TextStyle(
                    color: _muted,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<int>(
                  initialValue: _years,
                  decoration: InputDecoration(
                    labelText: 'Projection period',
                    border: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(14),
                    ),
                  ),
                  items: [1, 5, 10].map((year) {
                    return DropdownMenuItem<int>(
                      value: year,
                      child: Text(
                        '$year '
                        '${year == 1 ? 'year' : 'years'}',
                      ),
                    );
                  }).toList(),
                  onChanged:
                      _loading
                      ? null
                      : (value) {
                          if (value == null) return;

                          setState(() {
                            _years = value;
                            _result = null;
                            _error = null;
                          });
                        },
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed:
                        _loading
                        ? null
                        : _loadAssessment,
                    icon: const Icon(
                      Icons.timeline_rounded,
                    ),
                    label: Text(
                      _loading
                          ? 'Loading…'
                          : 'Calculate estimate',
                    ),
                  ),
                ),
              ],
            ),
            if (_loading)
              const Padding(
                padding: EdgeInsets.all(20),
                child: Center(
                  child:
                      CircularProgressIndicator(),
                ),
              ),
            if (_error != null)
              _section(
                'Unable to load assessment',
                [
                  Text(
                    _error!,
                    style: const TextStyle(
                      color: Color(0xFFFFB4AB),
                    ),
                  ),
                ],
              ),
            if (result != null) ...[
              _section(
                'Primary shoreline projection',
                [
                  _detailRow(
                    'Period',
                    '${result['years_ahead']} years',
                  ),
                  _detailRow(
                    'Annual erosion rate',
                    _measurement(
                      result['primary_rate_m_yr'],
                      'm/year',
                    ),
                  ),
                  _detailRow(
                    'Estimated retreat',
                    _measurement(
                      result['primary_retreat_m'],
                      'm',
                    ),
                  ),
                  _detailRow(
                    'Rate source',
                    _sourceName(
                      result['projection_source'],
                    ),
                  ),
                ],
              ),
              _section(
                'Linear Regression · Experimental',
                [
                  _detailRow(
                    'Predicted erosion rate',
                    _measurement(
                      result[
                          'lr_experimental_rate_m_yr'],
                      'm/year',
                    ),
                  ),
                  _detailRow(
                    'Estimated LR retreat',
                    _measurement(
                      result[
                          'lr_experimental_retreat_m'],
                      'm',
                    ),
                  ),
                  const Text(
                    'An experimental estimate is shown '
                    'only when available for this location.',
                    style: TextStyle(
                      color: _muted,
                      fontSize: 12,
                      height: 1.6,
                    ),
                  ),
                ],
              ),
            ],
            const Text(
              'Risk categories are based on the project '
              'dataset. Estimated retreat is a distance, '
              'not a mapped future shoreline position. '
              'Changing the projection period does not '
              'change the risk category.',
              style: TextStyle(
                color: _muted,
                fontSize: 12,
                height: 1.6,
              ),
            ),
          ],
        ),
      ),
    );
  }
}