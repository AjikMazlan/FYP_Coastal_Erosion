import 'package:flutter/material.dart';

import 'coastal_risk_screen.dart';
import 'shoreline_prediction_screen.dart';

// USB phone connection: adb reverse tcp:5000 tcp:5000.
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
              eyebrow: 'RISK CATEGORIES',
              accentColor: const Color(0xFF36D6BE),
              subtitle: 'Explore coastal erosion risk across Terengganu',
              icon: Icons.map_outlined,
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) =>
                        const CoastalRiskMapScreen(baseUrl: coastalApiBaseUrl),
                  ),
                );
              },
            ),
            FeatureCard(
              title: 'Shoreline Prediction',
              eyebrow: 'FUTURE SHORELINE',
              accentColor: const Color(0xFF87B8FF),
              subtitle: 'Explore shoreline projections for 1–10 years',
              icon: Icons.timeline_rounded,
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

// MAIN MENU CARD
class FeatureCard extends StatelessWidget {
  final String title;
  final String eyebrow;
  final String subtitle;
  final IconData icon;
  final Color accentColor;
  final VoidCallback onTap;

  const FeatureCard({
    super.key,
    required this.title,
    required this.eyebrow,
    required this.subtitle,
    required this.icon,
    required this.accentColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF152238),
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 16),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: const BorderSide(color: Color(0xFF29384D)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Ink(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              accentColor.withValues(alpha: 0.10),
              const Color(0xFF152238),
            ],
          ),
        ),
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(13),
                  decoration: BoxDecoration(
                    color: accentColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Icon(icon, color: accentColor, size: 28),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        eyebrow,
                        style: TextStyle(
                          color: accentColor,
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 1.2,
                        ),
                      ),
                      const SizedBox(height: 7),
                      Text(
                        title,
                        style: const TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFFF0F5FA),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        subtitle,
                        style: const TextStyle(
                          color: Color(0xFFA8B8CC),
                          fontSize: 13,
                          height: 1.5,
                        ),
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Text(
                            'Explore',
                            style: TextStyle(
                              color: accentColor,
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Icon(
                            Icons.arrow_forward_rounded,
                            color: accentColor,
                            size: 17,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
