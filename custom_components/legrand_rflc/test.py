import asyncio
import logging
import argparse
import sys

# Configure logging to see what lc7001 is doing under the hood
logging.basicConfig(
    level=logging.DEBUG, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

try:
    #import lc7001.aio
    import aio
except ImportError:
    print("Error: The 'lc7001' package is not installed in this Python environment.")
    print("Run 'pip install lc7001' before running this script.")
    sys.exit(1)

async def test_lc7001_connection(host, password=None):
    kwargs = {"loop_timeout": -1}
    if password:
        kwargs["key"] = aio.hash_password(password.encode())
    
    print(f"\n--- Testing Connector for {host} ---")
    try:
        # Connector is used by config_flow to test the connection and fetch MAC
        connector = aio.Connector(host, **kwargs)
        
        # We wrap it in a timeout because config_flow might be hanging here
        print("Waiting for connector.loop()... (10s timeout)")
        mac = await asyncio.wait_for(connector.loop(), timeout=60.0)
        print(f"[SUCCESS] Successfully connected via Connector! MAC Address: {mac}")
        
    except asyncio.TimeoutError:
        print("[ERROR] Connection timed out waiting for connector.loop()")
        return
    except aio.Authenticator.Error as error:
        print(f"[ERROR] Authentication failed: {error}")
        return
    except Exception as e:
        print(f"[ERROR] An error occurred during connection: {e}")
        return

    print(f"\n--- Testing Hub for {host} ---")
    try:
        # Hub is used by __init__ to manage the ongoing connection and state
        hub = aio.Hub(host, **kwargs)
        
        async def on_authenticated(*args):
            print("[SUCCESS] Hub Event: EVENT_AUTHENTICATED received!")
            print("[INFO] Requesting list of zones from controller...")
            # Request the list of zones/lights
            await hub.send(hub.compose_list_zones())
            
        async def on_zone_added(*args):
            print(f"[INFO] Hub Event: EVENT_ZONE_ADDED received: {args}")
            
        async def on_list_zones(*args):
            message = args[0]
            print(f"[INFO] Received ListZones with {len(message.get('ZoneList', []))} zones.")
            for zone in message.get("ZoneList", []):
                zid = zone.get("ZID")
                if zid is not None:
                    await hub.send(hub.compose_report_zone_properties(zid))
                    
        async def on_report_zone_properties(*args):
            message = args[0]
            zid = message.get('ZID')
            props = message.get('PropertyList', {})
            name = props.get('Name', 'Unknown')
            device_type = props.get('DeviceType', 'Unknown')
            power = props.get('Power', False)
            level = props.get('PowerLevel', 0)
            print(f"[ZONE] ZID: {zid} | Name: '{name}' | Type: {device_type} | Power: {'ON' if power else 'OFF'} | Level: {level}%")

        hub.once(hub.EVENT_AUTHENTICATED, on_authenticated)
        hub.on(hub.EVENT_ZONE_ADDED, on_zone_added)
        hub.on(hub.EVENT_LIST_ZONES, on_list_zones)
        hub.on(hub.EVENT_REPORT_ZONE_PROPERTIES, on_report_zone_properties)
        
        print("Starting hub.loop(). Waiting 5 seconds to receive initial events...")
        hub_task = asyncio.create_task(hub.loop())
        
        await asyncio.sleep(5)
        
        print("Test complete. Cancelling hub loop...")
        await hub.cancel()
        hub_task.cancel()
        
    except Exception as e:
        print(f"❌ An error occurred while testing Hub: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Legrand LC7001 connection outside of Home Assistant")
    parser.add_argument("host", help="IP address or hostname of the LC7001 controller")
    parser.add_argument("--password", "-p", help="Password for the controller (if configured)", default=None)
    args = parser.parse_args()
    
    try:
        asyncio.run(test_lc7001_connection(args.host, args.password))
    except KeyboardInterrupt:
        print("\nTest cancelled by user.")