#!/usr/bin/env python3
"""
ARES (Autonomous Rescue & Emergency System)
UGV Robot Telemetry & Path Simulator
Simulates Orange Pi Zero 3 sending sensor data to the Central PC.
"""

import time
import math
import random
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Simulation Arena Settings
MAP_SIZE = 400  # 400x400 cm grid
OBSTACLE_CENTER = (200, 200)
OBSTACLE_RADIUS = 35

# High-fidelity Hazard Positions
GAS_SOURCE = (320, 80)
FIRE_SOURCE = (80, 320)

# Waypoints for Autonomous Mode
WAYPOINTS = [
    (50, 50),
    (200, 45),
    (350, 50),
    (350, 200),
    (350, 350),
    (200, 355),
    (50, 350),
    (50, 200)
]

class UGVSimulator:
    def __init__(self, backend_url="https://127.0.0.1:5001/api/telemetry"):
        self.backend_url = backend_url
        self.mode = "Autonomous"  # "Autonomous" or "Manual"
        self.x = 50.0
        self.y = 50.0
        self.waypoint_idx = 0
        self.speed = 6.0  # units per step
        
        # Manual command states
        self.manual_command = "STOP"
        self.simulate_fire_override = False
        self.simulate_gas_override = False

        # Baseline environmental values
        self.base_temp = 22.5
        self.base_hum = 48.0

    def step_simulation(self):
        """Calculates the next state of the robot based on the mode."""
        if self.mode == "Autonomous":
            # Move towards current waypoint
            target_x, target_y = WAYPOINTS[self.waypoint_idx]
            dx = target_x - self.x
            dy = target_y - self.y
            distance = math.sqrt(dx**2 + dy**2)

            if distance < self.speed:
                # Arrived at waypoint, move to next
                self.x = target_x
                self.y = target_y
                self.waypoint_idx = (self.waypoint_idx + 1) % len(WAYPOINTS)
            else:
                # Interpolate step
                self.x += (dx / distance) * self.speed
                self.y += (dy / distance) * self.speed
        else:
            # Manual Control Movement
            step_size = 8.0
            if self.manual_command == "FORWARD":
                self.y = max(10.0, self.y - step_size)
            elif self.manual_command == "BACKWARD":
                self.y = min(MAP_SIZE - 10.0, self.y + step_size)
            elif self.manual_command == "LEFT":
                self.x = max(10.0, self.x - step_size)
            elif self.manual_command == "RIGHT":
                self.x = min(MAP_SIZE - 10.0, self.x + step_size)
            
            # Prevent manual driving directly inside the obstacle center pillar
            dist_to_pillar = math.sqrt((self.x - OBSTACLE_CENTER[0])**2 + (self.y - OBSTACLE_CENTER[1])**2)
            if dist_to_pillar < OBSTACLE_RADIUS + 5:
                # Push back slightly
                angle = math.atan2(self.y - OBSTACLE_CENTER[1], self.x - OBSTACLE_CENTER[0])
                self.x = OBSTACLE_CENTER[0] + (OBSTACLE_RADIUS + 8) * math.cos(angle)
                self.y = OBSTACLE_CENTER[1] + (OBSTACLE_RADIUS + 8) * math.sin(angle)

    def read_sensors(self):
        """Calculates sensor readings based on spatial relationships and overrides."""
        # 1. LiDAR Distance to closest boundary or obstacle
        dist_to_left = self.x
        dist_to_right = MAP_SIZE - self.x
        dist_to_top = self.y
        dist_to_bottom = MAP_SIZE - self.y
        dist_to_pillar = math.sqrt((self.x - OBSTACLE_CENTER[0])**2 + (self.y - OBSTACLE_CENTER[1])**2) - OBSTACLE_RADIUS
        
        lidar_dist = min(dist_to_left, dist_to_right, dist_to_top, dist_to_bottom, dist_to_pillar)
        # Prevent negative values and add minimal noise
        lidar_dist = max(1.0, lidar_dist) + random.uniform(-0.3, 0.3)

        # 2. Gas Sensors (MQ-9, MQ-135, MiCS-6814)
        dist_to_gas = math.sqrt((self.x - GAS_SOURCE[0])**2 + (self.y - GAS_SOURCE[1])**2)
        gas_factor = math.exp(-dist_to_gas / 65.0)

        mq9_val = 8.0 + 450.0 * gas_factor
        mq135_val = 22.0 + 800.0 * gas_factor
        mics_val = 0.12 + 6.5 * gas_factor

        # UI Force Gas Overrides
        if self.simulate_gas_override:
            mq9_val += 350.0 + random.uniform(0, 50)
            mq135_val += 600.0 + random.uniform(0, 100)
            mics_val += 4.5 + random.uniform(0, 1)

        # Add noise
        mq9_val = max(1.0, mq9_val + random.uniform(-0.5, 0.5))
        mq135_val = max(5.0, mq135_val + random.uniform(-1.0, 1.0))
        mics_val = max(0.05, mics_val + random.uniform(-0.01, 0.01))

        # 3. Flame Sensor (5 Channels)
        dist_to_fire = math.sqrt((self.x - FIRE_SOURCE[0])**2 + (self.y - FIRE_SOURCE[1])**2)
        flame_triggered = dist_to_fire < 65.0 or self.simulate_fire_override
        
        flame_array = [0, 0, 0, 0, 0]
        if flame_triggered:
            if self.simulate_fire_override:
                flame_array = [1, 1, 1, 1, 1]
            else:
                # Active channels based on distance to fire
                if dist_to_fire < 25.0:
                    flame_array = [1, 1, 1, 1, 1]
                elif dist_to_fire < 45.0:
                    flame_array = [0, 1, 1, 1, 0]
                else:
                    flame_array = [0, 0, 1, 0, 0]

        # 4. Temperature & Humidity (BME688)
        thermal_effect = math.exp(-dist_to_fire / 55.0)
        temp_reading = self.base_temp + (55.0 * thermal_effect)
        hum_reading = self.base_hum - (25.0 * thermal_effect)

        if self.simulate_fire_override:
            temp_reading = max(temp_reading, 68.5)
            hum_reading = min(hum_reading, 18.0)

        # Noise
        temp_reading += random.uniform(-0.15, 0.15)
        hum_reading += random.uniform(-0.3, 0.3)
        hum_reading = max(5.0, min(95.0, hum_reading))

        return {
            "lidar": round(lidar_dist, 1),
            "bme688": {
                "temperature": round(temp_reading, 2),
                "humidity": round(hum_reading, 2)
            },
            "gas": {
                "mq9": round(mq9_val, 2),
                "mq135": round(mq135_val, 2),
                "mics6814": round(mics_val, 3)
            },
            "flame": flame_array
        }

    def run(self):
        """Main loop that steps simulation and posts results."""
        print(f"Starting ARES UGV Simulator thread targeting: {self.backend_url}")
        while True:
            try:
                self.step_simulation()
                sensors = self.read_sensors()

                payload = {
                    "status": {
                        "mode": self.mode,
                        "position": {
                            "x": round(self.x, 1),
                            "y": round(self.y, 1)
                        }
                    },
                    "sensors": sensors
                }

                # Post telemetry to backend Flask server over TLS/HTTPS
                response = requests.post(self.backend_url, json=payload, timeout=0.8, verify=False)
                if response.status_code == 200:
                    data = response.json()
                    # Parse command states returned by Flask
                    self.mode = data.get("mode", "Autonomous")
                    self.manual_command = data.get("manual_command", "STOP")
                    self.simulate_fire_override = data.get("simulate_fire", False)
                    self.simulate_gas_override = data.get("simulate_gas", False)
                else:
                    print(f"[Simulator] Failed to send telemetry. Server responded: {response.status_code}")

            except requests.exceptions.RequestException as e:
                # Server might not be started yet, retry silently
                pass
            except Exception as e:
                print(f"[Simulator Error] {e}")

            time.sleep(0.5)

def start_simulator(backend_url="https://127.0.0.1:5001/api/telemetry"):
    sim = UGVSimulator(backend_url)
    sim.run()

if __name__ == "__main__":
    start_simulator()
