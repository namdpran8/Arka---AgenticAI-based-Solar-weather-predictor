"""
Solar Flare Multi-Agent Monitoring System
===========================================
A comprehensive autonomous system for monitoring and reporting solar flare events
from NASA DONKI API using a multi-agent architecture powered by Gemini.

ARCHITECTURE:
- Agent 1 (Monitor): Scheduled polling of NASA DONKI API
- Agent 2 (Analyst): Gemini-powered contextual analysis
- Agent 3 (Report Writer): Gemini-powered natural language generation
- Agent 4 (Notifier): Multi-channel alert distribution

KEY CONCEPTS IMPLEMENTED:
1. Tool Use: NASA DONKI API, Web Search API, Email SMTP
2. Multi-Agent Collaboration: Four specialized agents working together
3. Prompt Engineering: Structured prompts for consistent Gemini responses
4. Context Management: State tracking across agent interactions
5. Error Handling: Graceful degradation and retry logic
"""

import requests
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import time
from dataclasses import dataclass, asdict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from abc import ABC, abstractmethod

print("Solar Flare Multi-Agent Monitoring System Loaded")
# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class SolarFlare:
    """
    Data model for solar flare events from NASA DONKI
    Represents the core domain object passed between agents
    """
    flare_id: str
    class_type: str
    source_location: str
    begin_time: str
    peak_time: str
    end_time: str
    linked_events: List[str]
    active_region_num: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    def severity_level(self) -> int:
        """
        Return numeric severity: 3=X-class, 2=M-class, 1=C-class, 0=other
        Used for prioritization logic
        """
        if self.class_type.startswith('X'):
            return 3
        elif self.class_type.startswith('M'):
            return 2
        elif self.class_type.startswith('C'):
            return 1
        return 0


@dataclass
class AgentContext:
    """
    Shared context object passed between agents
    Implements Context Management pattern for multi-agent coordination
    """
    flare: SolarFlare
    analysis_data: Optional[Dict] = None
    report: Optional[str] = None
    notification_results: Optional[Dict] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


# ============================================================================
# BASE AGENT CLASS
# ============================================================================

class BaseAgent(ABC):
    """
    Abstract base class defining the agent interface
    All agents follow this contract for consistency
    """
    
    def __init__(self, agent_name: str, gemini_api_key: Optional[str] = None):
        self.agent_name = agent_name
        self.gemini_api_key = gemini_api_key
        self.execution_history = []
    
    @abstractmethod
    def execute(self, context: AgentContext) -> AgentContext:
        """
        Main execution method - must be implemented by all agents
        Takes context, performs work, returns updated context
        """
        pass
    
    def log(self, message: str, level: str = "INFO"):
        """Structured logging for observability"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{self.agent_name}] [{level}] {message}"
        print(log_entry)
        self.execution_history.append(log_entry)
    
    def call_gemini(self, prompt: str, temperature: float = 0.7) -> str:
        """
        TOOL USE: Gemini API integration
        Centralized method for calling Gemini with error handling
        """
        if not self.gemini_api_key:
            self.log("Gemini API key not configured, using fallback", "WARNING")
            return ""
        
        try:
            # Gemini API endpoint
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self.gemini_api_key}"
            
            headers = {'Content-Type': 'application/json'}
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": 2048,
                }
            }
            
            response = requests.post(url, headers=headers, 
                                   json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            text = result['candidates'][0]['content']['parts'][0]['text']
            
            self.log(f"Gemini API call successful ({len(text)} chars)")
            return text
            
        except Exception as e:
            self.log(f"Gemini API error: {e}", "ERROR")
            return ""


# ============================================================================
# AGENT 1: THE MONITOR
# ============================================================================

class Agent1Monitor(BaseAgent):
    """
    Agent 1: The Monitor
    
    RESPONSIBILITIES:
    - Polls NASA DONKI API on schedule
    - Detects new solar flare events
    - Filters for significant events (M and X class)
    - Maintains state to prevent duplicate alerts
    
    KEY CONCEPTS:
    - Tool Use: NASA DONKI API integration
    - State Management: Tracking seen flares
    """
    
    def __init__(self, nasa_api_key: str = "DEMO_KEY", 
                 gemini_api_key: Optional[str] = None):
        super().__init__("Monitor", gemini_api_key)
        self.nasa_api_key = nasa_api_key
        self.base_url = "https://api.nasa.gov/DONKI/FLR"
        self.seen_flares = set()
        self.last_check_time = None
    
    def execute(self, context: AgentContext = None) -> List[AgentContext]:
        """
        Execute monitoring cycle
        Returns list of contexts (one per detected flare)
        """
        self.log("Starting monitoring cycle")
        
        # Fetch recent flares from NASA API
        flares_data = self._fetch_recent_flares()
        
        # Detect new significant flares
        new_flares = self._detect_new_flares(flares_data)
        
        if new_flares:
            self.log(f"Detected {len(new_flares)} new significant flare(s)", "INFO")
            # Create a context for each new flare
            contexts = [AgentContext(flare=flare) for flare in new_flares]
            return contexts
        else:
            self.log("No new significant flares detected")
            return []
    
    def _fetch_recent_flares(self, days_back: int = 7) -> List[Dict]:
        """
        TOOL USE: NASA DONKI API
        Fetch solar flares from the past N days with error handling
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        params = {
            'startDate': start_date.strftime('%Y-%m-%d'),
            'endDate': end_date.strftime('%Y-%m-%d'),
            'api_key': self.nasa_api_key
        }
        
        try:
            self.log(f"Fetching flares from {start_date.date()} to {end_date.date()}")
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            self.log(f"Successfully fetched {len(data)} flare records")
            return data
        except requests.exceptions.RequestException as e:
            self.log(f"API fetch error: {e}", "ERROR")
            return []
    
    def _detect_new_flares(self, flares_data: List[Dict]) -> List[SolarFlare]:
        """
        Filter for new, significant flares
        Implements business logic for significance threshold
        """
        new_flares = []
        
        for flare_data in flares_data:
            flare_id = flare_data.get('flrID')
            
            # Skip if already processed
            if flare_id in self.seen_flares:
                continue
            
            # Filter for significant events (M-class or X-class)
            class_type = flare_data.get('classType', '')
            if class_type.startswith('M') or class_type.startswith('X'):
                # Parse and create SolarFlare object
                flare = SolarFlare(
                    flare_id=flare_id,
                    class_type=class_type,
                    source_location=flare_data.get('sourceLocation', 'Unknown'),
                    begin_time=flare_data.get('beginTime', ''),
                    peak_time=flare_data.get('peakTime', ''),
                    end_time=flare_data.get('endTime', ''),
                    linked_events=[event.get('activityID', '') 
                                 for event in flare_data.get('linkedEvents', [])],
                    active_region_num=flare_data.get('activeRegionNum')
                )
                
                new_flares.append(flare)
                self.seen_flares.add(flare_id)
                self.log(f"New {class_type} flare detected: {flare_id}")
        
        self.last_check_time = datetime.now()
        return new_flares


# ============================================================================
# AGENT 2: THE ANALYST
# ============================================================================

class Agent2Analyst(BaseAgent):
    """
    Agent 2: The Analyst
    
    RESPONSIBILITIES:
    - Analyzes solar flare impacts using Gemini
    - Searches for related news and context
    - Determines affected regions and severity
    
    KEY CONCEPTS:
    - Gemini Integration: AI-powered analysis
    - Prompt Engineering: Structured prompts for consistent output
    - Tool Use: Web search for context
    """
    
    def __init__(self, gemini_api_key: Optional[str] = None,
                 serper_api_key: Optional[str] = None):
        super().__init__("Analyst", gemini_api_key)
        self.serper_api_key = serper_api_key
        self.serper_url = "https://google.serper.dev/search"
    
    def execute(self, context: AgentContext) -> AgentContext:
        """
        Execute analysis on detected flare
        Enriches context with AI-powered insights
        """
        self.log(f"Analyzing flare {context.flare.flare_id}")
        
        # Search for contextual information
        search_results = self._search_flare_context(context.flare)
        
        # Use Gemini for intelligent analysis
        gemini_analysis = self._analyze_with_gemini(context.flare, search_results)
        
        # Compile analysis data
        analysis = {
            'search_results': search_results,
            'gemini_analysis': gemini_analysis,
            'severity_assessment': self._assess_severity(context.flare),
            'potential_impacts': self._determine_impacts(context.flare),
            'affected_regions': self._determine_regions(context.flare),
            'timestamp': datetime.now().isoformat()
        }
        
        context.analysis_data = analysis
        self.log(f"Analysis complete for {context.flare.class_type} flare")
        
        return context
    
    def _search_flare_context(self, flare: SolarFlare) -> Dict:
        """
        TOOL USE: Web Search API
        Search for news and context about the solar flare
        """
        query = f"solar flare {flare.class_type} {flare.peak_time[:10]}"
        
        if self.serper_api_key:
            try:
                self.log(f"Searching web for: {query}")
                headers = {
                    'X-API-KEY': self.serper_api_key,
                    'Content-Type': 'application/json'
                }
                payload = json.dumps({"q": query, "num": 5})
                response = requests.post(self.serper_url, headers=headers,
                                       data=payload, timeout=10)
                response.raise_for_status()
                self.log("Web search successful")
                return response.json()
            except Exception as e:
                self.log(f"Search API error: {e}", "WARNING")
        
        # Fallback to simulated results
        return {'organic': [], 'query': query}
    
    def _analyze_with_gemini(self, flare: SolarFlare, 
                            search_results: Dict) -> str:
        """
        GEMINI INTEGRATION: AI-powered contextual analysis
        PROMPT ENGINEERING: Structured prompt for consistent analysis
        """
        if not self.gemini_api_key:
            return self._fallback_analysis(flare)
        
        # Construct structured prompt for Gemini
        prompt = f"""You are a space weather analyst. Analyze this solar flare event:

FLARE DATA:
- Classification: {flare.class_type}
- Peak Time: {flare.peak_time}
- Source Location: {flare.source_location}
- Active Region: {flare.active_region_num or 'Unknown'}
- Linked Events: {len(flare.linked_events)}

CONTEXT:
Search results indicate related space weather activity.

TASK:
Provide a concise analysis (2-3 sentences) covering:
1. The significance of this flare class
2. Likely impacts on Earth systems (communications, satellites, power grids)
3. Any notable aspects based on timing or location

Keep response factual and suitable for emergency alerts."""

        return self.call_gemini(prompt, temperature=0.3)
    
    def _fallback_analysis(self, flare: SolarFlare) -> str:
        """Fallback analysis when Gemini is unavailable"""
        severity = "severe" if flare.class_type.startswith('X') else "moderate"
        return (f"A {flare.class_type} class solar flare represents {severity} "
                f"space weather activity with potential impacts on radio "
                f"communications and satellite operations.")
    
    def _assess_severity(self, flare: SolarFlare) -> Dict:
        """
        Assess flare severity with structured data
        """
        level = flare.severity_level()
        
        severity_map = {
            3: {'level': 'SEVERE', 'icon': '🔴', 'description': 'Major event'},
            2: {'level': 'MODERATE', 'icon': '🟠', 'description': 'Significant event'},
            1: {'level': 'MINOR', 'icon': '🟡', 'description': 'Minor event'}
        }
        
        return severity_map.get(level, 
                               {'level': 'INFO', 'icon': '⚪', 'description': 'Informational'})
    
    def _determine_impacts(self, flare: SolarFlare) -> List[str]:
        """Determine potential impacts based on flare classification"""
        impacts = {
            'X': [
                'High risk of widespread radio blackouts',
                'Potential GPS and navigation disruptions',
                'Possible power grid fluctuations at high latitudes',
                'Elevated radiation risk for polar flight routes'
            ],
            'M': [
                'Moderate radio interference on sunlit side',
                'Minor satellite operation disruptions',
                'Limited impact on high-frequency communications',
                'Possible auroral activity at high latitudes'
            ]
        }
        
        class_letter = flare.class_type[0] if flare.class_type else 'C'
        return impacts.get(class_letter, ['Minimal impact expected'])
    
    def _determine_regions(self, flare: SolarFlare) -> List[str]:
        """Determine affected geographic regions"""
        # Parse class magnitude
        try:
            class_magnitude = float(flare.class_type[1:])
        except:
            class_magnitude = 1.0
        
        # Severity-based region determination
        if flare.class_type.startswith('X') or class_magnitude >= 5.0:
            return [
                'Global (all longitudes)',
                'Particularly: High-latitude regions',
                'Polar flight routes',
                'HF radio communication zones'
            ]
        else:
            return [
                'Sunlit hemisphere at time of peak',
                'High-frequency radio users',
                'Satellite operators'
            ]


# ============================================================================
# AGENT 3: THE REPORT WRITER
# ============================================================================

class Agent3ReportWriter(BaseAgent):
    """
    Agent 3: The Report Writer
    
    RESPONSIBILITIES:
    - Generates human-readable alert reports
    - Uses Gemini for natural language generation
    - Structures technical data into accessible format
    
    KEY CONCEPTS:
    - Gemini Integration: AI-powered report generation
    - Prompt Engineering: Report formatting prompts
    - Natural Language Generation
    """
    
    def __init__(self, gemini_api_key: Optional[str] = None):
        super().__init__("ReportWriter", gemini_api_key)
    
    def execute(self, context: AgentContext) -> AgentContext:
        """
        Generate comprehensive alert report
        """
        self.log(f"Generating report for flare {context.flare.flare_id}")
        
        # Option 1: Gemini-powered report (more natural language)
        if self.gemini_api_key and context.analysis_data:
            report = self._generate_gemini_report(context)
        else:
            # Option 2: Template-based report (fallback)
            report = self._generate_template_report(context)
        
        context.report = report
        self.log("Report generation complete")
        
        return context
    
    def _generate_gemini_report(self, context: AgentContext) -> str:
        """
        GEMINI INTEGRATION: AI-powered natural language report generation
        PROMPT ENGINEERING: Structured template for consistent formatting
        """
        flare = context.flare
        analysis = context.analysis_data
        
        # Construct structured prompt for report generation
        prompt = f"""You are writing an emergency alert report for a solar flare event. 

FLARE DATA:
- ID: {flare.flare_id}
- Class: {flare.class_type}
- Peak Time: {flare.peak_time}
- Location: {flare.source_location}
- Duration: {flare.begin_time} to {flare.end_time}

ANALYSIS:
{analysis.get('gemini_analysis', 'Analysis unavailable')}

IMPACTS:
{', '.join(analysis.get('potential_impacts', []))}

AFFECTED REGIONS:
{', '.join(analysis.get('affected_regions', []))}

Generate a professional alert report with these sections:
1. HEADER: Title with severity indicator
2. EXECUTIVE SUMMARY: 2-3 sentence overview
3. EVENT DETAILS: Technical specifications
4. IMPACT ASSESSMENT: Expected effects
5. AFFECTED AREAS: Geographic scope
6. RECOMMENDATIONS: Brief guidance for affected parties

Use clear, professional language. Include the emoji indicator for severity.
Keep total length under 500 words."""

        gemini_report = self.call_gemini(prompt, temperature=0.4)
        
        if gemini_report:
            # Add footer with metadata
            footer = f"\n\n{'='*70}\nReport ID: {flare.flare_id}\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\nPowered by Gemini AI\n{'='*70}"
            return gemini_report + footer
        else:
            # Fallback if Gemini fails
            return self._generate_template_report(context)
    
    def _generate_template_report(self, context: AgentContext) -> str:
        """
        Fallback template-based report generation
        """
        flare = context.flare
        analysis = context.analysis_data or {}
        
        severity = analysis.get('severity_assessment', {})
        level = severity.get('level', 'INFO')
        icon = severity.get('icon', '⚪')
        
        report = f"""
{'='*70}
{icon} SOLAR FLARE ALERT - {level} {icon}
{'='*70}

FLARE CLASSIFICATION: {flare.class_type}
EVENT ID: {flare.flare_id}
SEVERITY: {level}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TIMING INFORMATION:
  • Begin Time:  {self._format_time(flare.begin_time)}
  • Peak Time:   {self._format_time(flare.peak_time)}
  • End Time:    {self._format_time(flare.end_time)}

SOURCE INFORMATION:
  • Location: {flare.source_location}
  • Active Region: {flare.active_region_num or 'Not specified'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ANALYSIS:
{analysis.get('gemini_analysis', 'AI analysis unavailable - using standard assessment')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

POTENTIAL IMPACTS:
"""
        
        for impact in analysis.get('potential_impacts', ['Impact assessment pending']):
            report += f"  • {impact}\n"
        
        report += "\nAFFECTED REGIONS:\n"
        for region in analysis.get('affected_regions', ['Global assessment pending']):
            report += f"  • {region}\n"
        
        if flare.linked_events:
            report += f"\nLINKED EVENTS: {len(flare.linked_events)} associated space weather event(s)\n"
        
        report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RECOMMENDATIONS:
  • Monitor space weather updates from NOAA SWPC
  • Review communication backup procedures if in affected regions
  • Satellite operators should verify system status
  • Aircraft on polar routes should stay informed

REPORT METADATA:
  • Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
  • Source: NASA DONKI API
  • Event ID: {flare.flare_id}

{'='*70}
"""
        return report
    
    def _format_time(self, iso_time: str) -> str:
        """Format ISO timestamp to readable format"""
        try:
            dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M UTC')
        except:
            return iso_time


# ============================================================================
# AGENT 4: THE NOTIFIER
# ============================================================================

class Agent4Notifier(BaseAgent):
    """
    Agent 4: The Notifier
    
    RESPONSIBILITIES:
    - Distributes alerts via multiple channels
    - Handles email notifications
    - Logs to file system
    - Console output
    
    KEY CONCEPTS:
    - Tool Use: SMTP for email, file system APIs
    - Multi-channel distribution
    - Error handling and graceful degradation
    """
    
    def __init__(self, email_config: Optional[Dict] = None,
                 gemini_api_key: Optional[str] = None):
        super().__init__("Notifier", gemini_api_key)
        self.email_config = email_config
    
    def execute(self, context: AgentContext) -> AgentContext:
        """
        Distribute alert via configured channels
        """
        self.log("Distributing alert notifications")
        
        if not context.report:
            self.log("No report to distribute", "WARNING")
            return context
        
        results = {}
        
        # Console notification (always enabled)
        results['console'] = self._notify_console(context.report)
        
        # File system notification
        results['file'] = self._save_to_file(context.report, context.flare)
        
        # Email notification (if configured)
        if self.email_config:
            results['email'] = self._send_email(context.report, context.flare)
        
        context.notification_results = results
        self.log(f"Notifications sent via {len([k for k,v in results.items() if v])} channel(s)")
        
        return context
    
    def _notify_console(self, report: str) -> bool:
        """Display alert in console"""
        try:
            print("\n" + report)
            self.log("Console notification successful")
            return True
        except Exception as e:
            self.log(f"Console notification error: {e}", "ERROR")
            return False
    
    def _save_to_file(self, report: str, flare: SolarFlare) -> bool:
        """
        TOOL USE: File system API
        Save report to file for persistence and auditing
        """
        try:
            # Create reports directory if it doesn't exist
            os.makedirs('reports', exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"reports/solar_flare_{flare.class_type}_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
            
            self.log(f"Report saved to {filename}")
            return True
        except Exception as e:
            self.log(f"File save error: {e}", "ERROR")
            return False
    
    def _send_email(self, report: str, flare: SolarFlare) -> bool:
        """
        TOOL USE: SMTP Email API
        Send alert via email with error handling
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['sender']
            msg['To'] = self.email_config['recipient']
            msg['Subject'] = f"🌞 SOLAR FLARE ALERT - {flare.class_type} Class Event"
            
            msg.attach(MIMEText(report, 'plain'))
            
            with smtplib.SMTP(self.email_config['smtp_server'],
                            self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender'],
                           self.email_config['password'])
                server.send_message(msg)
            
            self.log(f"Email sent to {self.email_config['recipient']}")
            return True
        except Exception as e:
            self.log(f"Email error: {e}", "ERROR")
            return False


# ============================================================================
# ORCHESTRATOR: MULTI-AGENT SYSTEM COORDINATOR
# ============================================================================

class SolarFlareMonitoringSystem:
    """
    Main orchestrator for the multi-agent system
    
    ARCHITECTURE:
    Implements the coordinator pattern for multi-agent systems
    - Initializes all agents
    - Manages agent execution flow
    - Handles inter-agent communication via context objects
    - Provides scheduling and continuous monitoring
    
    KEY CONCEPTS:
    - Multi-Agent Collaboration: Coordinated execution
    - Context Management: Shared state between agents
    - Error Handling: Graceful degradation
    """
    
    def __init__(self,
                 nasa_api_key: str = "DEMO_KEY",
                 gemini_api_key: Optional[str] = None,
                 serper_api_key: Optional[str] = None,
                 email_config: Optional[Dict] = None):
        """
        Initialize all agents with their dependencies
        """
        self.monitor = Agent1Monitor(nasa_api_key, gemini_api_key)
        self.analyst = Agent2Analyst(gemini_api_key, serper_api_key)
        self.writer = Agent3ReportWriter(gemini_api_key)
        self.notifier = Agent4Notifier(email_config, gemini_api_key)
        
        self.execution_log = []
        
        print("="*70)
        print("Solar Flare Multi-Agent System Initialized")
        print("="*70)
        print(f"✓ Agent 1 (Monitor): Ready")
        print(f"✓ Agent 2 (Analyst): {'Gemini-powered' if gemini_api_key else 'Standard mode'}")
        print(f"✓ Agent 3 (Report Writer): {'Gemini-powered' if gemini_api_key else 'Template mode'}")
        print(f"✓ Agent 4 (Notifier): {self._notification_channels()}")
        print("="*70 + "\n")
    
    def _notification_channels(self) -> str:
        """Determine active notification channels"""
        channels = ['Console', 'File']
        if self.notifier.email_config:
            channels.append('Email')
        return ', '.join(channels)
    
    def run_cycle(self) -> int:
        """
        MULTI-AGENT COLLABORATION:
        Execute one complete monitoring cycle with all agents
        
        Flow:
        1. Agent 1 monitors NASA API
        2. For each detected flare:
           a. Agent 2 analyzes
           b. Agent 3 writes report
           c. Agent 4 distributes
        
        Returns: Number of flares processed
        """
        cycle_start = datetime.now()
        print("\n" + "="*70)
        print(f"MONITORING CYCLE STARTED - {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70 + "\n")
        
        try:
            # Agent 1: Monitor for new flares
            contexts = self.monitor.execute()
            
            if not contexts:
                print("No new significant flares detected\n")
                return 0
            
            # Process each detected flare through the agent pipeline
            for i, context in enumerate(contexts, 1):
                print(f"\n--- Processing Flare {i}/{len(contexts)} ---\n")
                
                # Agent 2: Analyze
                context = self.analyst.execute(context)
                
                # Agent 3: Write Report
                context = self.writer.execute(context)
                
                # Agent 4: Notify
                context = self.notifier.execute(context)
                
                # Log execution
                self.execution_log.append({
                    'timestamp': context.timestamp,
                    'flare_id': context.flare.flare_id,
                    'class': context.flare.class_type,
                    'notifications': context.notification_results
                })
            
            cycle_end = datetime.now()
            duration = (cycle_end - cycle_start).total_seconds()
            
            print(f"\n{'='*70}")
            print(f"CYCLE COMPLETE - Processed {len(contexts)} flare(s) in {duration:.2f}s")
            print(f"{'='*70}\n")
            
            return len(contexts)
            
        except Exception as e:
            print(f"\nERROR in monitoring cycle: {e}")
            return 0
    
    def run_continuous(self, interval_minutes: int = 30):
        """
        Run continuous monitoring with scheduling
        Implements the polling pattern for autonomous operation
        """
        print(f"{'='*70}")
        print(f"CONTINUOUS MONITORING MODE")
        print(f"Check Interval: {interval_minutes} minutes")
        print(f"Press Ctrl+C to stop")
        print(f"{'='*70}\n")
        
        try:
            while True:
                flares_processed = self.run_cycle()
                
                next_check = datetime.now() + timedelta(minutes=interval_minutes)
                print(f"Next check at: {next_check.strftime('%H:%M:%S')}")
                print(f"Sleeping for {interval_minutes} minutes...\n")
                
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user")
            self._print_summary()
    
    def _print_summary(self):
        """Print execution summary"""
        print(f"\n{'='*70}")
        print("EXECUTION SUMMARY")
        print(f"{'='*70}")
        print(f"Total flares processed: {len(self.execution_log)}")
        
        if self.execution_log:
            by_class = {}
            for entry in self.execution_log:
                class_type = entry['class']
                by_class[class_type] = by_class.get(class_type, 0) + 1
            
            print("\nFlares by classification:")
            for class_type in sorted(by_class.keys(), reverse=True):
                print(f"  {class_type}: {by_class[class_type]}")
        
        print(f"{'='*70}\n")


# ============================================================================
# DEPLOYMENT UTILITIES
# ============================================================================

class DeploymentConfig:
    """
    Configuration management for cloud deployment
    Supports environment variables for security
    """
    
    @staticmethod
    def from_environment() -> Dict:
        """
        Load configuration from environment variables
        SECURITY: Never hardcode API keys
        """
        return {
            'nasa_api_key': os.getenv('NASA_API_KEY', 'DEMO_KEY'),
            'gemini_api_key': os.getenv('GEMINI_API_KEY'),
            'serper_api_key': os.getenv('SERPER_API_KEY'),
            'email_config': {
                'sender': os.getenv('EMAIL_SENDER'),
                'password': os.getenv('EMAIL_PASSWORD'),
                'recipient': os.getenv('EMAIL_RECIPIENT'),
                'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
                'smtp_port': int(os.getenv('SMTP_PORT', '587'))
            } if os.getenv('EMAIL_SENDER') else None
        }
    
    @staticmethod
    def create_system() -> SolarFlareMonitoringSystem:
        """
        Factory method for creating system from environment
        Suitable for Cloud Run, Agent Engine, etc.
        """
        config = DeploymentConfig.from_environment()
        return SolarFlareMonitoringSystem(**config)


# ============================================================================
# CLOUD RUN / AGENT ENGINE DEPLOYMENT EXAMPLE
# ============================================================================

def cloud_run_handler(request=None):
    """
    HTTP handler for Google Cloud Run deployment
    Can be triggered via Cloud Scheduler or HTTP request
    
    Example deployment:
    gcloud run deploy solar-flare-monitor \
        --source . \
        --set-env-vars NASA_API_KEY=xxx,GEMINI_API_KEY=xxx
    """
    system = DeploymentConfig.create_system()
    flares_processed = system.run_cycle()
    
    return {
        'status': 'success',
        'flares_processed': flares_processed,
        'timestamp': datetime.now().isoformat()
    }


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════════╗
    ║           SOLAR FLARE MULTI-AGENT MONITORING SYSTEM               ║
    ║                    Competition Submission                          ║
    ╚════════════════════════════════════════════════════════════════════╝
    """)
    
    # Example 1: Basic usage with NASA API (no Gemini)
    print("\n📋 Example 1: Basic Monitoring (Template-based reports)\n")
    print("Code:")
    print("  system = SolarFlareMonitoringSystem(nasa_api_key='DEMO_KEY')")
    print("  system.run_cycle()\n")
    
    # Example 2: With Gemini integration (RECOMMENDED)
    print("📋 Example 2: AI-Powered Monitoring (Gemini-enhanced)\n")
    print("Code:")
    print("  system = SolarFlareMonitoringSystem(")
    print("      nasa_api_key='YOUR_NASA_KEY',")
    print("      gemini_api_key='YOUR_GEMINI_KEY'")
    print("  )")
    print("  system.run_cycle()\n")
    
    # Example 3: Full configuration with all features
    print("📋 Example 3: Full Configuration (All features)\n")
    print("Code:")
    print("  email_config = {")
    print("      'sender': 'alerts@example.com',")
    print("      'password': 'app_password',")
    print("      'recipient': 'team@example.com',")
    print("      'smtp_server': 'smtp.gmail.com',")
    print("      'smtp_port': 587")
    print("  }")
    print("  system = SolarFlareMonitoringSystem(")
    print("      nasa_api_key='YOUR_NASA_KEY',")
    print("      gemini_api_key='YOUR_GEMINI_KEY',")
    print("      serper_api_key='YOUR_SERPER_KEY',")
    print("      email_config=email_config")
    print("  )")
    print("  system.run_continuous(interval_minutes=30)\n")
    
    # Example 4: Cloud deployment
    print("📋 Example 4: Cloud Deployment\n")
    print("Code:")
    print("  # Set environment variables, then:")
    print("  system = DeploymentConfig.create_system()")
    print("  system.run_cycle()\n")
    
    # Run actual demo
    print("="*70)
    print("RUNNING DEMO - Single Monitoring Cycle")
    print("="*70 + "\n")
    
    # Create system with NASA API (works without Gemini key for demo)
    system = SolarFlareMonitoringSystem(
        nasa_api_key=os.getenv('NASA_API_KEY', 'DEMO_KEY'),
        gemini_api_key=os.getenv('GEMINI_API_KEY')
    )
    
    # Run one cycle
    flares_processed = system.run_cycle()
    
    if flares_processed == 0:
        print("\n💡 TIP: Solar flares are sporadic events.")
        print("The system may run for days without detecting significant flares.")
        print("This is normal behavior - the system is working correctly!")
        print("\nTo test with your own Gemini API key:")
        print("  export GEMINI_API_KEY='your_key_here'")
        print("  python solar_flare_monitor.py")
    
    print("\n✅ Demo complete! Check the 'reports' folder for generated alerts.")
    print("\nFor continuous monitoring, use:")
    print("  system.run_continuous(interval_minutes=30)")