/**
 * Jewellery Box Interactive - Management Node Server
 * ===================================================
 *
 * Runs on Ubuntu Server on Qotom Q355G4-S02 or Intel NUC with managed switch.
 * Responsibilities:
 *   - Listen for OSC messages from 3 plinths (ports 5000-5002)
 *   - Enforce button interlocks (only one plinth active at a time)
 *   - Forward plinth events to Q-SYS Core (port 5010/5011)
 *   - Receive motor commands from Q-SYS and route to plinths
 *   - Handle network reconnection after cable/power loss
 *   - Log all events for debugging and maintenance
 *   - Provide status endpoint for monitoring
 *
 * OSC Protocol:
 *   Receive from plinths (5000-5002):
 *     /plinth/[1-3]/button/press
 *     /plinth/[1-3]/button/release
 *     /plinth/[1-3]/maintenance [0|1]
 *
 *   Send to plinths:
 *     /plinth/[1-3]/motor/open
 *     /plinth/[1-3]/motor/close
 *     /plinth/[1-3]/led [0-255]
 *     /plinth/[1-3]/enable
 *     /plinth/[1-3]/disable
 *
 *   Send to Q-SYS (port 5010):
 *     /plinth/[1-3]/button/press
 *     /plinth/[1-3]/maintenance [0|1]
 *
 *   Receive from Q-SYS (port 5011):
 *     /plinth/[1-3]/motor/open
 *     /plinth/[1-3]/motor/close
 *     /system/reset
 *
 * Author: Development Team
 * Date: 2025-12-18
 */

const dgram = require('dgram');
const http = require('http');
const fs = require('fs');
const path = require('path');

// ============================================================================
// Configuration
// ============================================================================

class Config {
  static PLINTH_COUNT = 3;
  static PLINTH_BASE_PORT = 5000;  // 5000, 5001, 5002
  
  // Management node
  static MGMT_PORT = 5010;  // Receive from Q-SYS
  static MGMT_SEND_PORT = 5011;  // Send to Q-SYS
  static QSYS_IP = process.env.QSYS_IP || '192.168.10.50';  // Q-SYS Core IP per network spec
  
  // HTTP status endpoint
  static HTTP_PORT = 3000;
  
  // Reconnection
  static PLINTH_HEARTBEAT_TIMEOUT = 30000;  // 30 seconds
  static QSYS_HEARTBEAT_TIMEOUT = 60000;  // 60 seconds
  
  // Logging
  static LOG_FILE = '/var/log/jewellery_box_mgmt.log';
  static LOG_LEVEL = process.env.LOG_LEVEL || 'info';
}

// ============================================================================
// Logging
// ============================================================================

class Logger {
  static levels = { debug: 0, info: 1, warn: 2, error: 3 };
  static currentLevel = Logger.levels[Config.LOG_LEVEL];
  
  static _ensureLogDir() {
    const dir = path.dirname(Config.LOG_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }
  
  static _format(level, msg) {
    const time = new Date().toISOString().split('T')[1].slice(0, 8);
    return `[${time}] [${level.toUpperCase()}] ${msg}`;
  }
  
  static _write(level, msg) {
    const formatted = Logger._format(level, msg);
    console.log(formatted);
    
    if (Logger.levels[level] >= Logger.currentLevel) {
      try {
        Logger._ensureLogDir();
        fs.appendFileSync(Config.LOG_FILE, formatted + '\n');
      } catch (e) {
        console.error(`Failed to write to log: ${e.message}`);
      }
    }
  }
  
  static debug(msg) { if (this.currentLevel <= this.levels.debug) this._write('debug', msg); }
  static info(msg) { if (this.currentLevel <= this.levels.info) this._write('info', msg); }
  static warn(msg) { if (this.currentLevel <= this.levels.warn) this._write('warn', msg); }
  static error(msg) { if (this.currentLevel <= this.levels.error) this._write('error', msg); }
}

// ============================================================================
// OSC Message Format
// ============================================================================

class OSCMessage {
  constructor(address, args = []) {
    this.address = address;
    this.args = args;
  }
  
  static parse(buffer) {
    // Simple OSC parser (handles string and int types)
    let offset = 0;
    
    // Read address (null-terminated string, padded to 4-byte boundary)
    let address = '';
    while (buffer[offset] !== 0) {
      address += String.fromCharCode(buffer[offset]);
      offset++;
    }
    offset = Math.ceil((offset + 1) / 4) * 4;
    
    // Read type tags (null-terminated string, padded)
    let types = '';
    while (buffer[offset] !== 0) {
      types += String.fromCharCode(buffer[offset]);
      offset++;
    }
    offset = Math.ceil((offset + 1) / 4) * 4;
    
    // Parse arguments
    const args = [];
    for (let i = 1; i < types.length; i++) {  // Skip ','
      if (types[i] === 'i') {
        args.push(buffer.readInt32BE(offset));
        offset += 4;
      } else if (types[i] === 'f') {
        args.push(buffer.readFloatBE(offset));
        offset += 4;
      } else if (types[i] === 's') {
        let str = '';
        while (buffer[offset] !== 0) {
          str += String.fromCharCode(buffer[offset]);
          offset++;
        }
        offset = Math.ceil((offset + 1) / 4) * 4;
        args.push(str);
      }
    }
    
    return new OSCMessage(address, args);
  }
  
  toBuffer() {
    // Build OSC message
    const buffers = [];
    
    // Address
    const addressBuf = Buffer.alloc(4 * Math.ceil((this.address.length + 1) / 4));
    addressBuf.write(this.address);
    buffers.push(addressBuf);
    
    // Type tag
    let typeStr = ',';
    for (const arg of this.args) {
      if (typeof arg === 'number') {
        typeStr += Number.isInteger(arg) ? 'i' : 'f';
      } else if (typeof arg === 'string') {
        typeStr += 's';
      }
    }
    const typeBuf = Buffer.alloc(4 * Math.ceil((typeStr.length + 1) / 4));
    typeBuf.write(typeStr);
    buffers.push(typeBuf);
    
    // Arguments
    for (let i = 0; i < this.args.length; i++) {
      const arg = this.args[i];
      if (typeof arg === 'number') {
        const argBuf = Buffer.alloc(4);
        if (Number.isInteger(arg)) {
          argBuf.writeInt32BE(arg, 0);
        } else {
          argBuf.writeFloatBE(arg, 0);
        }
        buffers.push(argBuf);
      } else if (typeof arg === 'string') {
        const argBuf = Buffer.alloc(4 * Math.ceil((arg.length + 1) / 4));
        argBuf.write(arg);
        buffers.push(argBuf);
      }
    }
    
    return Buffer.concat(buffers);
  }
}

// ============================================================================
// Plinth State Tracker
// ============================================================================

class PlinthState {
  constructor(id) {
    this.id = id;
    this.port = Config.PLINTH_BASE_PORT + id - 1;
    this.address = `192.168.1.1${id}`;  // Adjust to match your network
    
    this.buttonPressed = false;
    this.maintenanceActive = false;
    this.motorState = 'idle';
    this.ledBrightness = 0;
    this.enabled = true;
    
    this.lastHeartbeat = Date.now();
    this.connected = false;
  }
  
  isAlive() {
    return (Date.now() - this.lastHeartbeat) < Config.PLINTH_HEARTBEAT_TIMEOUT;
  }
  
  updateHeartbeat() {
    this.lastHeartbeat = Date.now();
  }
}

// ============================================================================
// Q-SYS Connector
// ============================================================================

class QSYSConnector {
  constructor() {
    this.ip = Config.QSYS_IP;
    this.port = Config.MGMT_SEND_PORT;
    this.lastHeartbeat = Date.now();
    this.client = dgram.createSocket('udp4');
    this.connected = false;
    
    Logger.info(`Q-SYS connector initialized (${this.ip}:${this.port})`);
  }
  
  send(message) {
    const buffer = message.toBuffer();
    this.client.send(buffer, 0, buffer.length, this.port, this.ip, (err) => {
      if (err) {
        Logger.error(`Failed to send to Q-SYS: ${err.message}`);
        this.connected = false;
      } else {
        this.connected = true;
        this.lastHeartbeat = Date.now();
      }
    });
  }
  
  forwardButtonPress(plinthId) {
    this.send(new OSCMessage(`/plinth/${plinthId}/button/press`, [1]));
    Logger.debug(`Forwarded button press from plinth ${plinthId} to Q-SYS`);
  }
  
  forwardMaintenance(plinthId, state) {
    this.send(new OSCMessage(`/plinth/${plinthId}/maintenance`, [state]));
    Logger.debug(`Forwarded maintenance state ${state} from plinth ${plinthId} to Q-SYS`);
  }
  
  isAlive() {
    return (Date.now() - this.lastHeartbeat) < Config.QSYS_HEARTBEAT_TIMEOUT;
  }
}

// ============================================================================
// Interlock Manager
// ============================================================================

class InterlockManager {
  constructor(plinths) {
    this.plinths = plinths;
    this.activePlinth = null;
    this.sequenceActive = false;
  }
  
  activatePlinth(plinthId) {
    if (this.activePlinth !== null && this.activePlinth !== plinthId) {
      Logger.warn(`Plinth ${plinthId} button pressed but plinth ${this.activePlinth} is active`);
      return false;
    }
    
    this.activePlinth = plinthId;
    this.sequenceActive = true;
    
    Logger.info(`Plinth ${plinthId} activated`);
    
    // Disable other plinths
    for (const p of this.plinths) {
      if (p.id !== plinthId) {
        this.disablePlinth(p.id);
      }
    }
    
    return true;
  }
  
  disablePlinth(plinthId) {
    const plinth = this.plinths.find(p => p.id === plinthId);
    if (plinth) {
      plinth.enabled = false;
      Logger.debug(`Plinth ${plinthId} disabled`);
    }
  }
  
  enablePlinth(plinthId) {
    const plinth = this.plinths.find(p => p.id === plinthId);
    if (plinth) {
      plinth.enabled = true;
      Logger.debug(`Plinth ${plinthId} enabled`);
    }
  }
  
  deactivatePlinth(plinthId) {
    if (this.activePlinth === plinthId) {
      this.activePlinth = null;
      this.sequenceActive = false;
      
      Logger.info(`Plinth ${plinthId} sequence complete`);
      
      // Re-enable all plinths
      for (const p of this.plinths) {
        this.enablePlinth(p.id);
      }
    }
  }
}

// ============================================================================
// Management Node Server
// ============================================================================

class ManagementNodeServer {
  constructor() {
    // Initialize plinths
    this.plinths = [];
    for (let i = 1; i <= Config.PLINTH_COUNT; i++) {
      this.plinths.push(new PlinthState(i));
    }
    
    // Initialize components
    this.qsys = new QSYSConnector();
    this.interlock = new InterlockManager(this.plinths);
    
    // UDP servers
    this.plinthServers = [];
    this.mgmtServer = null;
    
    // HTTP status server
    this.httpServer = null;
  }
  
  start() {
    Logger.info('Management Node starting...');
    
    // Start plinth listeners
    for (let i = 0; i < Config.PLINTH_COUNT; i++) {
      this.startPlinthListener(i + 1);
    }
    
    // Start management server (receive from Q-SYS)
    this.startMgmtServer();
    
    // Start HTTP status endpoint
    this.startHTTPServer();
    
    // Start health monitor
    this.startHealthMonitor();
    
    Logger.info('Management Node ready');
  }
  
  startPlinthListener(plinthId) {
    const port = Config.PLINTH_BASE_PORT + plinthId - 1;
    const server = dgram.createSocket('udp4');
    
    server.on('message', (msg, rinfo) => {
      try {
        const osc = OSCMessage.parse(msg);
        this.handlePlinthMessage(plinthId, osc, rinfo);
      } catch (e) {
        Logger.error(`Failed to parse OSC from plinth ${plinthId}: ${e.message}`);
      }
    });
    
    server.on('error', (err) => {
      Logger.error(`Plinth ${plinthId} server error: ${err.message}`);
    });
    
    server.bind(port, () => {
      Logger.info(`Listening to plinth ${plinthId} on port ${port}`);
    });
    
    this.plinthServers.push(server);
  }
  
  startMgmtServer() {
    this.mgmtServer = dgram.createSocket('udp4');
    
    this.mgmtServer.on('message', (msg, rinfo) => {
      try {
        const osc = OSCMessage.parse(msg);
        this.handleQSYSMessage(osc, rinfo);
      } catch (e) {
        Logger.error(`Failed to parse OSC from Q-SYS: ${e.message}`);
      }
    });
    
    this.mgmtServer.on('error', (err) => {
      Logger.error(`Management server error: ${err.message}`);
    });
    
    this.mgmtServer.bind(Config.MGMT_PORT, () => {
      Logger.info(`Management server listening on port ${Config.MGMT_PORT}`);
    });
  }
  
  startHTTPServer() {
    this.httpServer = http.createServer((req, res) => {
      if (req.url === '/status' && req.method === 'GET') {
        const status = {
          timestamp: new Date().toISOString(),
          plinths: this.plinths.map(p => ({
            id: p.id,
            connected: p.isAlive(),
            buttonPressed: p.buttonPressed,
            maintenanceActive: p.maintenanceActive,
            motorState: p.motorState,
            ledBrightness: p.ledBrightness,
            enabled: p.enabled
          })),
          qsys: {
            connected: this.qsys.isAlive(),
            ip: this.qsys.ip,
            port: this.qsys.port
          },
          interlock: {
            activePlinth: this.interlock.activePlinth,
            sequenceActive: this.interlock.sequenceActive
          }
        };
        
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(status, null, 2));
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    });
    
    this.httpServer.listen(Config.HTTP_PORT, () => {
      Logger.info(`HTTP status server on port ${Config.HTTP_PORT}`);
    });
  }
  
  handlePlinthMessage(plinthId, osc, rinfo) {
    const plinth = this.plinths[plinthId - 1];
    plinth.updateHeartbeat();
    plinth.connected = true;
    
    Logger.debug(`Received from plinth ${plinthId}: ${osc.address}`);
    
    if (osc.address === `/plinth/${plinthId}/button/press`) {
      plinth.buttonPressed = true;
      
      if (this.interlock.activatePlinth(plinthId)) {
        this.qsys.forwardButtonPress(plinthId);
        
        // Enable LED
        this.sendToPlinth(plinthId, new OSCMessage(`/plinth/${plinthId}/led`, [200]));
      } else {
        // Button disabled due to interlock
        this.sendToPlinth(plinthId, new OSCMessage(`/plinth/${plinthId}/led`, [0]));
      }
    
    } else if (osc.address === `/plinth/${plinthId}/button/release`) {
      plinth.buttonPressed = false;
      this.interlock.deactivatePlinth(plinthId);
    
    } else if (osc.address === `/plinth/${plinthId}/maintenance`) {
      plinth.maintenanceActive = osc.args[0] === 1;
      this.qsys.forwardMaintenance(plinthId, plinth.maintenanceActive ? 1 : 0);
      Logger.info(`Plinth ${plinthId} maintenance: ${plinth.maintenanceActive}`);
    }
  }
  
  handleQSYSMessage(osc, rinfo) {
    Logger.debug(`Received from Q-SYS: ${osc.address}`);
    
    // Extract plinth ID from address (e.g., /plinth/1/motor/open)
    const match = osc.address.match(/\/plinth\/(\d)/);
    if (!match) return;
    
    const plinthId = parseInt(match[1]);
    
    if (osc.address.includes('/motor/')) {
      if (osc.address.endsWith('/open')) {
        this.sendToPlinth(plinthId, new OSCMessage(`/plinth/${plinthId}/motor/open`, []));
        Logger.info(`Q-SYS: Open motor on plinth ${plinthId}`);
      } else if (osc.address.endsWith('/close')) {
        this.sendToPlinth(plinthId, new OSCMessage(`/plinth/${plinthId}/motor/close`, []));
        Logger.info(`Q-SYS: Close motor on plinth ${plinthId}`);
      }
    } else if (osc.address === '/system/reset') {
      Logger.warn('Q-SYS: System reset command');
      this.interlock.activePlinth = null;
      this.interlock.sequenceActive = false;
      for (const p of this.plinths) {
        this.interlock.enablePlinth(p.id);
      }
    }
  }
  
  sendToPlinth(plinthId, osc) {
    const plinth = this.plinths[plinthId - 1];
    const buffer = osc.toBuffer();
    
    const client = dgram.createSocket('udp4');
    client.send(buffer, 0, buffer.length, plinth.port, plinth.address, (err) => {
      if (err) {
        Logger.error(`Failed to send to plinth ${plinthId}: ${err.message}`);
      } else {
        Logger.debug(`Sent to plinth ${plinthId}: ${osc.address}`);
      }
      client.close();
    });
  }
  
  startHealthMonitor() {
    setInterval(() => {
      for (const plinth of this.plinths) {
        const wasConnected = plinth.connected;
        const isNowConnected = plinth.isAlive();
        
        if (wasConnected && !isNowConnected) {
          Logger.warn(`Plinth ${plinth.id} heartbeat timeout`);
          plinth.connected = false;
        } else if (!wasConnected && isNowConnected) {
          Logger.info(`Plinth ${plinth.id} reconnected`);
          plinth.connected = true;
        }
      }
      
      if (!this.qsys.isAlive()) {
        Logger.warn('Q-SYS heartbeat timeout');
      }
    }, 5000);
  }
  
  stop() {
    Logger.info('Shutting down management node...');
    
    for (const server of this.plinthServers) {
      server.close();
    }
    
    if (this.mgmtServer) this.mgmtServer.close();
    if (this.httpServer) this.httpServer.close();
    if (this.qsys.client) this.qsys.client.close();
  }
}

// ============================================================================
// Main Entry Point
// ============================================================================

const server = new ManagementNodeServer();

process.on('SIGINT', () => {
  Logger.info('Interrupted by user');
  server.stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  Logger.info('Terminated');
  server.stop();
  process.exit(0);
});

process.on('uncaughtException', (err) => {
  Logger.error(`Uncaught exception: ${err.message}`);
  server.stop();
  process.exit(1);
});

server.start();
