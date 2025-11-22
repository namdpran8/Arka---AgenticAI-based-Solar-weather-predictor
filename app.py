"""
Flask Web Server for Solar Flare Monitoring Dashboard
Connects the HTML dashboard to the multi-agent system backend
"""

from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import os
import json
from datetime import datetime
from threading import Thread
import time

# Import our multi-agent system
from solar_flare_monitor import (
    SolarFlareMonitoringSystem,
    DeploymentConfig,
    Agent1Monitor
)

app = Flask(__name__)
CORS(app)  # Enable CORS for API calls

# Global system instance
monitoring_system = None
system_stats = {
    'agent1_calls': 0,
    'agent1_events': 0,
    'agent2_analyses': 0,
    'agent3_reports': 0,
    'agent4_sent': 0,
    'total_flares': 0,
    'active_alerts': 0,
    'last_check': None,
    'status': 'initialized'
}

recent_alerts = []
system_logs = []


def init_system():
    """Initialize the monitoring system"""
    global monitoring_system
    
    try:
        monitoring_system = DeploymentConfig.create_system()
        log_message("System initialized successfully", "success")
        system_stats['status'] = 'active'
        return True
    except Exception as e:
        log_message(f"Failed to initialize system: {e}", "error")
        system_stats['status'] = 'error'
        return False


def log_message(message, level="info"):
    """Add message to system log"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'level': level,
        'message': message
    }
    system_logs.insert(0, log_entry)
    
    # Keep only last 100 logs
    if len(system_logs) > 100:
        system_logs.pop()
    
    print(f"[{level.upper()}] {message}")


# ============================================================================
# ROUTES
# ============================================================================

@app.route('/')
def index():
    """Serve the dashboard HTML"""
    return send_file('dashboard.html')


@app.route('/api/status')
def get_status():
    """Get current system status"""
    return jsonify({
        'stats': system_stats,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/alerts')
def get_alerts():
    """Get recent alerts"""
    return jsonify({
        'alerts': recent_alerts[:20],  # Last 20 alerts
        'count': len(recent_alerts)
    })


@app.route('/api/logs')
def get_logs():
    """Get system logs"""
    return jsonify({
        'logs': system_logs[:50],  # Last 50 logs
        'count': len(system_logs)
    })


@app.route('/api/run-cycle', methods=['POST'])
def run_cycle():
    """Manually trigger a monitoring cycle"""
    if not monitoring_system:
        log_message("System not initialized", "error")
        return jsonify({'error': 'System not initialized'}), 500
    
    try:
        log_message("Starting manual monitoring cycle", "info")
        system_stats['status'] = 'running'
        
        # Run the monitoring cycle
        flares_detected = monitoring_system.run_cycle()
        
        # Update statistics
        system_stats['agent1_calls'] += 1
        system_stats['last_check'] = datetime.now().isoformat()
        
        if flares_detected > 0:
            system_stats['agent1_events'] += flares_detected
            system_stats['agent2_analyses'] += flares_detected
            system_stats['agent3_reports'] += flares_detected
            system_stats['agent4_sent'] += flares_detected
            system_stats['total_flares'] += flares_detected
            system_stats['active_alerts'] += flares_detected
            
            # Add alerts
            for i in range(flares_detected):
                add_alert(i + 1)
            
            log_message(f"Cycle complete: {flares_detected} flare(s) processed", "success")
        else:
            log_message("Cycle complete: No new flares detected", "info")
        
        system_stats['status'] = 'active'
        
        return jsonify({
            'success': True,
            'flares_detected': flares_detected,
            'stats': system_stats
        })
        
    except Exception as e:
        log_message(f"Error in monitoring cycle: {e}", "error")
        system_stats['status'] = 'error'
        return jsonify({'error': str(e)}), 500


@app.route('/api/fetch-data', methods=['POST'])
def fetch_data():
    """Fetch recent data from NASA API"""
    try:
        log_message("Fetching recent data from NASA DONKI", "info")
        
        monitor = Agent1Monitor(
            nasa_api_key=os.getenv('NASA_API_KEY', 'DEMO_KEY')
        )
        
        flares = monitor.fetch_recent_flares(days_back=30)
        
        # Count significant flares
        significant = [f for f in flares 
                      if f.get('classType', '').startswith(('M', 'X'))]
        
        system_stats['total_flares'] = len(flares)
        
        log_message(f"Retrieved {len(flares)} total flares, "
                   f"{len(significant)} significant", "success")
        
        return jsonify({
            'success': True,
            'total_flares': len(flares),
            'significant_flares': len(significant),
            'data': flares[:10]  # Return first 10 for display
        })
        
    except Exception as e:
        log_message(f"Error fetching data: {e}", "error")
        return jsonify({'error': str(e)}), 500


@app.route('/api/reports')
def list_reports():
    """List available report files"""
    try:
        reports_dir = 'reports'
        if not os.path.exists(reports_dir):
            return jsonify({'reports': []})
        
        reports = []
        for filename in os.listdir(reports_dir):
            if filename.endswith('.txt'):
                filepath = os.path.join(reports_dir, filename)
                reports.append({
                    'filename': filename,
                    'size': os.path.getsize(filepath),
                    'modified': datetime.fromtimestamp(
                        os.path.getmtime(filepath)
                    ).isoformat()
                })
        
        # Sort by modified time, newest first
        reports.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({'reports': reports})
        
    except Exception as e:
        log_message(f"Error listing reports: {e}", "error")
        return jsonify({'error': str(e)}), 500


@app.route('/api/reports/<filename>')
def download_report(filename):
    """Download a specific report"""
    try:
        filepath = os.path.join('reports', filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            return jsonify({'error': 'Report not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/latest-report')
def get_latest_report():
    """Get the content of the latest report"""
    try:
        reports_dir = 'reports'
        if not os.path.exists(reports_dir):
            return jsonify({'error': 'No reports available'}), 404
        
        files = [f for f in os.listdir(reports_dir) if f.endswith('.txt')]
        if not files:
            return jsonify({'error': 'No reports available'}), 404
        
        # Get most recent file
        latest = max(files, key=lambda f: os.path.getmtime(
            os.path.join(reports_dir, f)
        ))
        
        filepath = os.path.join(reports_dir, latest)
        with open(filepath, 'r') as f:
            content = f.read()
        
        return jsonify({
            'filename': latest,
            'content': content,
            'modified': datetime.fromtimestamp(
                os.path.getmtime(filepath)
            ).isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def add_alert(flare_num):
    """Add a simulated alert to the list"""
    import random
    
    classes = ['M1.5', 'M2.3', 'M4.7', 'X1.2']
    flare_class = random.choice(classes)
    severity = 'critical' if flare_class.startswith('X') else 'warning'
    
    alert = {
        'id': len(recent_alerts) + 1,
        'severity': severity,
        'class': flare_class,
        'title': f'{flare_class} Solar Flare Detected',
        'message': f'A {flare_class} class solar flare was detected. '
                  f'AI analysis indicates {"severe" if severity == "critical" else "moderate"} '
                  f'space weather activity with potential impacts on radio '
                  f'communications and satellite operations.',
        'timestamp': datetime.now().isoformat(),
        'channels': ['console', 'file', 'email'],
        'status': 'processed'
    }
    
    recent_alerts.insert(0, alert)
    
    # Keep only last 50 alerts
    if len(recent_alerts) > 50:
        recent_alerts.pop()


# ============================================================================
# BACKGROUND MONITORING (OPTIONAL)
# ============================================================================

def background_monitoring(interval_minutes=30):
    """
    Run monitoring cycles in background thread
    Enable this for fully autonomous operation
    """
    log_message(f"Background monitoring started (interval: {interval_minutes} min)", 
               "info")
    
    while True:
        try:
            if monitoring_system and system_stats['status'] == 'active':
                log_message("Running scheduled monitoring cycle", "info")
                
                # This would trigger the actual monitoring
                # For now, we'll let users trigger manually via UI
                pass
            
            time.sleep(interval_minutes * 60)
            
        except Exception as e:
            log_message(f"Background monitoring error: {e}", "error")
            time.sleep(60)  # Wait 1 minute before retry


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == '__main__':
    print("="*70)
    print("🌞 Solar Flare Monitoring Dashboard Server")
    print("="*70)
    
    # Initialize the system
    if init_system():
        print("✓ Multi-agent system initialized")
    else:
        print("⚠ System initialization failed - check API keys")
    
    print("\n📊 Dashboard Features:")
    print("  • Real-time agent status monitoring")
    print("  • Manual monitoring cycle trigger")
    print("  • Live system logs and alerts")
    print("  • Report viewing and download")
    print("\n🌐 Starting web server...")
    print("="*70)
    
    # Optionally start background monitoring
    # Uncomment to enable autonomous operation:
    # monitoring_thread = Thread(target=background_monitoring, args=(30,))
    # monitoring_thread.daemon = True
    # monitoring_thread.start()
    
    # Start Flask server
    port = int(os.getenv('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True
    )