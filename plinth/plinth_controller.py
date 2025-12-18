#!/usr/bin/env python3
"""
Jewellery Box Interactive - Plinth Controller
=============================================

Runs on Raspberry Pi 4 Model B per plinth. Handles:
  - GPIO input reading (button, maintenance switch)
  - Stepper motor control (STEP/DIR/ENABLE)
  - LED PWM output
  - OSC communication with management node
  - Maintenance mode (4-second hold)
  - State persistence and auto-reconnection

GPIO Mapping:
  GPIO17: Button input (debounced)
  GPIO27: Maintenance switch input
  GPIO22: LED PWM output
  GPIO23: Stepper STEP output
  GPIO24: Stepper DIR output
  GPIO25: Stepper ENABLE output

OSC Communication:
  Send to management node (port 5000-5005 depending on plinth ID):
    /plinth/[1-3]/button/press - button pressed
    /plinth/[1-3]/button/release - button released
    /plinth/[1-3]/maintenance - maintenance switch state (0/1)
  
  Receive from management node:
    /plinth/[1-3]/motor/open - open the motor
    /plinth/[1-3]/motor/close - close the motor
    /plinth/[1-3]/led [0-255] - set LED brightness
    /plinth/[1-3]/enable - enable button
    /plinth/[1-3]/disable - disable button

Author: Development Team
Date: 2025-12-18
"""

import sys
import time
import threading
import logging
import json
import os
from datetime import datetime
from collections import deque
from enum import Enum

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    # Running on non-Raspberry Pi or GPIO not available
    GPIO = None
    print("[WARN] RPi.GPIO not available; running in simulation mode")

try:
    from pythonosc import udp_client, osc_server
    from pythonosc.dispatcher import Dispatcher
except ImportError:
    print("[ERROR] python-osc not installed. Install with: pip install python-osc")
    sys.exit(1)

# ============================================================================
# Configuration
# ============================================================================

class PlinthConfig:
    """Plinth configuration."""
    PLINTH_ID = int(os.getenv('PLINTH_ID', '1'))
    
    # Network - 192.168.10.x subnet per system recommendations
    MGMT_NODE_IP = os.getenv('MGMT_NODE_IP', '192.168.10.1')
    MGMT_NODE_PORT = 5000 + PLINTH_ID - 1  # 5000, 5001, 5002 for plinths 1, 2, 3
    LOCAL_OSC_PORT = 6000 + PLINTH_ID - 1  # 6000, 6001, 6002 for plinths 1, 2, 3
    
    # GPIO pins
    GPIO_BUTTON = 17
    GPIO_MAINTENANCE = 27
    GPIO_LED = 22
    GPIO_MOTOR_STEP = 23
    GPIO_MOTOR_DIR = 24
    GPIO_MOTOR_ENABLE = 25
    
    # Button debouncing
    DEBOUNCE_DELAY = 0.02  # 20 ms
    MAINTENANCE_HOLD_TIME = 4.0  # 4 seconds to trigger maintenance
    
    # Motor control
    MOTOR_STEP_DELAY = 0.002  # 2 ms between steps (500 steps/sec)
    MOTOR_STEPS_OPEN = 1000  # Steps to fully open
    MOTOR_STEPS_CLOSE = 1000  # Steps to fully close
    
    # LED PWM
    LED_PWM_FREQ = 1000  # Hz
    LED_DEFAULT_BRIGHTNESS = 255
    
    # Reconnection
    RECONNECT_ATTEMPTS = 10
    RECONNECT_DELAY = 5.0  # seconds
    
    # Logging
    LOG_FILE = f"/var/log/plinth_{PLINTH_ID}.log"
    LOG_LEVEL = logging.INFO

# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging():
    """Configure logging to file and console."""
    logger = logging.getLogger(__name__)
    logger.setLevel(PlinthConfig.LOG_LEVEL)
    
    # Ensure log directory exists
    log_dir = os.path.dirname(PlinthConfig.LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # File handler
    try:
        file_handler = logging.FileHandler(PlinthConfig.LOG_FILE)
        file_handler.setLevel(PlinthConfig.LOG_LEVEL)
        logger.addHandler(file_handler)
    except PermissionError:
        print(f"[WARN] Cannot write to {PlinthConfig.LOG_FILE}; logging to console only")
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(PlinthConfig.LOG_LEVEL)
    
    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter) if log_dir else None
    
    return logger

logger = setup_logging()

# ============================================================================
# State Enums
# ============================================================================

class MotorState(Enum):
    """Motor state."""
    IDLE = 0
    OPENING = 1
    CLOSING = 2
    OPEN = 3
    CLOSED = 4
    ERROR = 5

class PlinthState(Enum):
    """Plinth overall state."""
    IDLE = 0
    ACTIVE = 1
    DISABLED = 2
    MAINTENANCE = 3

# ============================================================================
# GPIO Handler (Real or Simulated)
# ============================================================================

class GPIOHandler:
    """Handle GPIO operations with fallback to simulation."""
    
    def __init__(self):
        self.is_simulated = GPIO is None
        self.gpio_state = {}
        self.pulsing = False  # Track LED pulsing state
        
        if not self.is_simulated:
            self._init_real_gpio()
        else:
            logger.warning("Running in GPIO simulation mode (no RPi.GPIO)")
    
    def _init_real_gpio(self):
        """Initialize real GPIO."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # Setup inputs
            GPIO.setup(PlinthConfig.GPIO_BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PlinthConfig.GPIO_MAINTENANCE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
            # Setup outputs
            GPIO.setup(PlinthConfig.GPIO_LED, GPIO.OUT)
            GPIO.setup(PlinthConfig.GPIO_MOTOR_STEP, GPIO.OUT)
            GPIO.setup(PlinthConfig.GPIO_MOTOR_DIR, GPIO.OUT)
            GPIO.setup(PlinthConfig.GPIO_MOTOR_ENABLE, GPIO.OUT)
            
            # Initialize PWM for LED
            self.led_pwm = GPIO.PWM(PlinthConfig.GPIO_LED, PlinthConfig.LED_PWM_FREQ)
            self.led_pwm.start(0)
            
            logger.info("GPIO initialized (real hardware)")
        except Exception as e:
            logger.error(f"GPIO initialization failed: {e}")
            self.is_simulated = True
    
    def read_input(self, gpio_pin):
        """Read digital input (inverted for active-low buttons)."""
        if self.is_simulated:
            return self.gpio_state.get(gpio_pin, 0)
        try:
            value = GPIO.input(gpio_pin)
            return 0 if value else 1  # Invert (active-low)
        except Exception as e:
            logger.error(f"Error reading GPIO {gpio_pin}: {e}")
            return 0
    
    def write_output(self, gpio_pin, value):
        """Write digital output."""
        if self.is_simulated:
            self.gpio_state[gpio_pin] = value
            logger.debug(f"[SIM] GPIO {gpio_pin} = {value}")
            return
        try:
            GPIO.output(gpio_pin, value)
        except Exception as e:
            logger.error(f"Error writing GPIO {gpio_pin}: {e}")
    
    def set_led_brightness(self, brightness):
        """Set LED brightness via PWM (0-255)."""
        duty_cycle = (brightness / 255.0) * 100.0
        if self.is_simulated:
            self.gpio_state['led_brightness'] = brightness
            logger.debug(f"[SIM] LED brightness = {brightness} ({duty_cycle:.1f}%)")
            return
        try:
            self.led_pwm.ChangeDutyCycle(duty_cycle)
        except Exception as e:
            logger.error(f"Error setting LED brightness: {e}")
    
    def start_led_pulse(self, pulse_freq=2.0, max_brightness=255, min_brightness=50):
        """
        Start LED pulsing animation.
        
        Args:
            pulse_freq: Pulse frequency in Hz (default 2 Hz = 0.5s cycle)
            max_brightness: Maximum brightness (0-255)
            min_brightness: Minimum brightness (0-255)
        """
        if self.is_simulated:
            logger.debug(f"[SIM] LED pulse started (freq={pulse_freq}Hz, max={max_brightness}, min={min_brightness})")
            return
        
        def pulse_animation():
            """Run pulsing animation in loop."""
            cycle_time = 1.0 / pulse_freq
            half_cycle = cycle_time / 2.0
            step_duration = 0.02  # 20ms steps for smooth animation
            steps = int(half_cycle / step_duration)
            
            try:
                while self.pulsing:
                    # Fade in (min -> max)
                    brightness_range = max_brightness - min_brightness
                    for step in range(steps):
                        if not self.pulsing:
                            return
                        brightness = min_brightness + (brightness_range * step / steps)
                        self.set_led_brightness(int(brightness))
                        time.sleep(step_duration)
                    
                    # Fade out (max -> min)
                    for step in range(steps):
                        if not self.pulsing:
                            return
                        brightness = max_brightness - (brightness_range * step / steps)
                        self.set_led_brightness(int(brightness))
                        time.sleep(step_duration)
                
                # Stop pulsing - turn LED off
                self.set_led_brightness(0)
                logger.debug("LED pulse animation stopped")
            except Exception as e:
                logger.error(f"Error in LED pulse animation: {e}")
        
        self.pulsing = True
        pulse_thread = threading.Thread(target=pulse_animation, daemon=True)
        pulse_thread.start()
        logger.debug(f"LED pulse started (freq={pulse_freq}Hz)")
    
    def stop_led_pulse(self):
        """Stop LED pulsing animation."""
        self.pulsing = False
        logger.debug("LED pulse stop requested")
    
    def cleanup(self):
        """Clean up GPIO resources."""
        if not self.is_simulated:
            try:
                self.led_pwm.stop()
                GPIO.cleanup()
                logger.info("GPIO cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up GPIO: {e}")

# ============================================================================
# Button Debouncer
# ============================================================================

class ButtonDebouncer:
    """Debounce button input."""
    
    def __init__(self, gpio_handler, gpio_pin):
        self.gpio_handler = gpio_handler
        self.gpio_pin = gpio_pin
        self.last_stable_state = 0
        self.last_read_time = time.time()
        self.read_history = deque(maxlen=3)
    
    def read(self):
        """Read and debounce button state."""
        now = time.time()
        if now - self.last_read_time < PlinthConfig.DEBOUNCE_DELAY:
            return self.last_stable_state
        
        self.last_read_time = now
        current = self.gpio_handler.read_input(self.gpio_pin)
        self.read_history.append(current)
        
        # All recent reads must agree
        if len(self.read_history) == 3 and len(set(self.read_history)) == 1:
            self.last_stable_state = current
        
        return self.last_stable_state

# ============================================================================
# Stepper Motor Controller
# ============================================================================

class StepperMotor:
    """Control stepper motor via STEP/DIR/ENABLE pins."""
    
    def __init__(self, gpio_handler):
        self.gpio_handler = gpio_handler
        self.state = MotorState.IDLE
        self.current_position = 0  # 0 = closed, MOTOR_STEPS_OPEN = open
        self.target_position = 0
        self.lock = threading.Lock()
    
    def open(self):
        """Open the motor."""
        with self.lock:
            if self.state in [MotorState.IDLE, MotorState.CLOSED, MotorState.ERROR]:
                self.state = MotorState.OPENING
                self.target_position = PlinthConfig.MOTOR_STEPS_OPEN
                logger.info(f"Plinth {PlinthConfig.PLINTH_ID}: Motor opening")
                return True
        return False
    
    def close(self):
        """Close the motor."""
        with self.lock:
            if self.state in [MotorState.IDLE, MotorState.OPEN, MotorState.ERROR]:
                self.state = MotorState.CLOSING
                self.target_position = 0
                logger.info(f"Plinth {PlinthConfig.PLINTH_ID}: Motor closing")
                return True
        return False
    
    def stop(self):
        """Stop motor movement."""
        with self.lock:
            self.state = MotorState.IDLE
            self.gpio_handler.write_output(PlinthConfig.GPIO_MOTOR_ENABLE, 0)
    
    def execute_step(self):
        """Execute one step cycle (run in background thread)."""
        with self.lock:
            if self.state == MotorState.IDLE:
                return
            
            # Determine direction
            if self.current_position < self.target_position:
                direction = 1  # Open
                self.gpio_handler.write_output(PlinthConfig.GPIO_MOTOR_DIR, 1)
            else:
                direction = -1  # Close
                self.gpio_handler.write_output(PlinthConfig.GPIO_MOTOR_DIR, 0)
            
            # Enable motor, pulse step pin
            self.gpio_handler.write_output(PlinthConfig.GPIO_MOTOR_ENABLE, 1)
            self.gpio_handler.write_output(PlinthConfig.GPIO_MOTOR_STEP, 1)
            time.sleep(0.001)  # 1 ms pulse
            self.gpio_handler.write_output(PlinthConfig.GPIO_MOTOR_STEP, 0)
            
            # Update position
            self.current_position += direction
            
            # Check if target reached
            if self.current_position == self.target_position:
                self.state = MotorState.OPEN if direction == 1 else MotorState.CLOSED
                self.gpio_handler.write_output(PlinthConfig.GPIO_MOTOR_ENABLE, 0)
                logger.info(f"Plinth {PlinthConfig.PLINTH_ID}: Motor {'opened' if direction == 1 else 'closed'}")

# ============================================================================
# OSC Client (to Management Node)
# ============================================================================

class OSCClient:
    """Send OSC messages to management node."""
    
    def __init__(self):
        self.client = None
        self.reconnect_count = 0
        self._connect()
    
    def _connect(self):
        """Establish connection to management node."""
        try:
            self.client = udp_client.SimpleUDPClient(
                PlinthConfig.MGMT_NODE_IP,
                PlinthConfig.MGMT_NODE_PORT
            )
            logger.info(
                f"OSC client connected to {PlinthConfig.MGMT_NODE_IP}:"
                f"{PlinthConfig.MGMT_NODE_PORT}"
            )
            self.reconnect_count = 0
        except Exception as e:
            logger.error(f"Failed to connect OSC client: {e}")
            self.client = None
    
    def send_button_press(self):
        """Send button press event."""
        if self.client:
            try:
                self.client.send_message(f"/plinth/{PlinthConfig.PLINTH_ID}/button/press", 1)
            except Exception as e:
                logger.error(f"Error sending button press: {e}")
    
    def send_button_release(self):
        """Send button release event."""
        if self.client:
            try:
                self.client.send_message(f"/plinth/{PlinthConfig.PLINTH_ID}/button/release", 0)
            except Exception as e:
                logger.error(f"Error sending button release: {e}")
    
    def send_maintenance_state(self, state):
        """Send maintenance switch state."""
        if self.client:
            try:
                self.client.send_message(f"/plinth/{PlinthConfig.PLINTH_ID}/maintenance", state)
            except Exception as e:
                logger.error(f"Error sending maintenance state: {e}")
    
    def reconnect(self):
        """Attempt reconnection."""
        self.reconnect_count += 1
        if self.reconnect_count > PlinthConfig.RECONNECT_ATTEMPTS:
            logger.warning(f"Max reconnect attempts reached; will retry in {PlinthConfig.RECONNECT_DELAY}s")
            self.reconnect_count = 0
        self._connect()

# ============================================================================
# OSC Server (receive from Management Node)
# ============================================================================

class OSCServer:
    """Receive OSC commands from management node."""
    
    def __init__(self, stepper, gpio_handler, osc_client):
        self.stepper = stepper
        self.gpio_handler = gpio_handler
        self.osc_client = osc_client
        self.dispatcher = Dispatcher()
        self.server = None
        
        # Register handlers
        self._register_handlers()
        self._start_server()
    
    def _register_handlers(self):
        """Register OSC message handlers."""
        plinth_id = PlinthConfig.PLINTH_ID
        
        self.dispatcher.map(f"/plinth/{plinth_id}/motor/open", self._handle_motor_open)
        self.dispatcher.map(f"/plinth/{plinth_id}/motor/close", self._handle_motor_close)
        self.dispatcher.map(f"/plinth/{plinth_id}/led", self._handle_led)
        self.dispatcher.map(f"/plinth/{plinth_id}/led/pulse", self._handle_led_pulse)
        self.dispatcher.map(f"/plinth/{plinth_id}/led/off", self._handle_led_off)
        self.dispatcher.map(f"/plinth/{plinth_id}/enable", self._handle_enable)
        self.dispatcher.map(f"/plinth/{plinth_id}/disable", self._handle_disable)
    
    def _start_server(self):
        """Start OSC server thread."""
        try:
            self.server = osc_server.ThreadingOSCUDPServer(
                ("0.0.0.0", PlinthConfig.LOCAL_OSC_PORT),
                self.dispatcher
            )
            thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            thread.start()
            logger.info(f"OSC server listening on port {PlinthConfig.LOCAL_OSC_PORT}")
        except Exception as e:
            logger.error(f"Failed to start OSC server: {e}")
    
    def _handle_motor_open(self, addr, value):
        """Handle motor open command."""
        logger.info(f"Received motor open command")
        self.stepper.open()
    
    def _handle_motor_close(self, addr, value):
        """Handle motor close command."""
        logger.info(f"Received motor close command")
        self.stepper.close()
    
    def _handle_led(self, addr, brightness):
        """Handle LED brightness command."""
        brightness = max(0, min(255, int(brightness)))
        logger.debug(f"LED brightness set to {brightness}")
        self.gpio_handler.stop_led_pulse()  # Stop any ongoing pulse
        self.gpio_handler.set_led_brightness(brightness)
    
    def _handle_led_pulse(self, addr, value):
        """Handle LED pulsing command (bang type)."""
        logger.info("LED pulse effect started")
        # Pulse with 2Hz frequency, 255 max brightness, 50 min brightness
        self.gpio_handler.start_led_pulse(pulse_freq=2.0, max_brightness=255, min_brightness=50)
    
    def _handle_led_off(self, addr, value):
        """Handle LED off command."""
        logger.debug("LED turned off")
        self.gpio_handler.stop_led_pulse()  # Stop any ongoing pulse
        self.gpio_handler.set_led_brightness(0)
    
    def _handle_enable(self, addr, value):
        """Handle enable command."""
        logger.info("Plinth enabled")
        # Set LED to indicate enabled
        self.gpio_handler.set_led_brightness(100)
    
    def _handle_disable(self, addr, value):
        """Handle disable command."""
        logger.info("Plinth disabled")
        # Set LED to indicate disabled
        self.gpio_handler.set_led_brightness(0)
        self.stepper.stop()

# ============================================================================
# Main Controller
# ============================================================================

class PlinthController:
    """Main plinth controller."""
    
    def __init__(self):
        self.gpio_handler = GPIOHandler()
        self.stepper = StepperMotor(self.gpio_handler)
        self.button_debouncer = ButtonDebouncer(self.gpio_handler, PlinthConfig.GPIO_BUTTON)
        self.maint_debouncer = ButtonDebouncer(self.gpio_handler, PlinthConfig.GPIO_MAINTENANCE)
        self.osc_client = OSCClient()
        self.osc_server = OSCServer(self.stepper, self.gpio_handler, self.osc_client)
        
        # State tracking
        self.button_pressed = False
        self.maintenance_pressed = False
        self.button_press_time = None
        self.plinth_state = PlinthState.IDLE
        
        # Threads
        self.running = True
        self.input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self.motor_thread = threading.Thread(target=self._motor_loop, daemon=True)
        self.watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
    
    def start(self):
        """Start controller threads."""
        logger.info(f"Starting Plinth {PlinthConfig.PLINTH_ID} Controller")
        self.input_thread.start()
        self.motor_thread.start()
        self.watchdog_thread.start()
    
    def stop(self):
        """Stop controller gracefully."""
        logger.info("Stopping plinth controller")
        self.running = False
        self.stepper.stop()
        self.gpio_handler.cleanup()
        time.sleep(0.5)
    
    def _input_loop(self):
        """Monitor button and maintenance switch."""
        while self.running:
            try:
                # Read debounced button
                button = self.button_debouncer.read()
                
                if button and not self.button_pressed:
                    # Button pressed
                    self.button_pressed = True
                    self.button_press_time = time.time()
                    logger.info(f"Button pressed")
                    self.osc_client.send_button_press()
                
                elif not button and self.button_pressed:
                    # Button released
                    self.button_pressed = False
                    hold_time = time.time() - self.button_press_time
                    logger.info(f"Button released (held {hold_time:.2f}s)")
                    self.osc_client.send_button_release()
                
                # Maintenance mode (4-second hold)
                if self.button_pressed:
                    hold_time = time.time() - self.button_press_time
                    if hold_time > PlinthConfig.MAINTENANCE_HOLD_TIME:
                        logger.warning(f"Maintenance mode activated (button held {hold_time:.2f}s)")
                        self.plinth_state = PlinthState.MAINTENANCE
                        # Toggle motor open/close in maintenance
                        if self.stepper.state == MotorState.CLOSED:
                            self.stepper.open()
                        else:
                            self.stepper.close()
                
                # Read maintenance switch
                maint = self.maint_debouncer.read()
                if maint != self.maintenance_pressed:
                    self.maintenance_pressed = maint
                    logger.info(f"Maintenance switch: {maint}")
                    self.osc_client.send_maintenance_state(maint)
                
                time.sleep(0.01)  # 10 ms loop
            
            except Exception as e:
                logger.error(f"Error in input loop: {e}")
                time.sleep(0.1)
    
    def _motor_loop(self):
        """Drive stepper motor."""
        while self.running:
            try:
                self.stepper.execute_step()
                time.sleep(PlinthConfig.MOTOR_STEP_DELAY)
            except Exception as e:
                logger.error(f"Error in motor loop: {e}")
                time.sleep(0.1)
    
    def _watchdog_loop(self):
        """Monitor system health and reconnect if needed."""
        while self.running:
            try:
                # Check if OSC client is connected
                if not self.osc_client.client:
                    logger.warning("OSC client disconnected; attempting reconnect")
                    time.sleep(PlinthConfig.RECONNECT_DELAY)
                    self.osc_client.reconnect()
                
                time.sleep(5.0)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")
                time.sleep(5.0)

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point."""
    controller = PlinthController()
    
    try:
        controller.start()
        logger.info(f"Plinth {PlinthConfig.PLINTH_ID} running; press Ctrl+C to stop")
        
        # Keep running
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        controller.stop()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        controller.stop()
        sys.exit(1)

if __name__ == '__main__':
    main()
