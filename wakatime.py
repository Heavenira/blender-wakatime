bl_info = {
    "name": "WakaTime for Blender",
    "author": "Ezra Oppenheimer (Heavenira)",
    "version": (1, 0, 0),
    "blender": (3, 3, 0),
    "location": "Preferences > Add-ons > WakaTime for Blender",
    "description": "Analyze your Blender productivity using WakaTime.com",
    "category": "Development",
}

# this must match the add-on name, use '__package__'
# when defining this in a submodule of a python package.
NAME = __name__

import bpy
import time, base64, json, requests, threading
from bpy.types import Operator, AddonPreferences
from bpy.props import StringProperty, IntProperty, BoolProperty
from bpy.app.handlers import persistent

def log(message):
    time_string = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    if bpy.context.preferences.addons[NAME].preferences.enable_console:
        print(f"WAKATIME ({time_string}):", message)

def post_to_wakatime(api_key: str):
    def header(api_key: str):  # creates a header dictionary type using a WakaTime API key

        btoa = str(base64.b64encode(bytes(api_key, "utf-8")))[2:-1]  # converts API key to its base64 representation

        return {  # return the dict, using the WakaTime API specifications
            "Authorization": f"Basic {btoa}",
            "Content-Type": "applications/json"
        }

    def payload(project: str, entity: str, branch: str): # Creates a body dictionary type using Blender's current info.
        data = {  # prepare the dict, using the WakaTime API specifications
            "project": project,
            "entity": entity if entity != "" else "untitled.blend",
            "branch": branch,
            "type": "app",
            "category": "coding",
            "language": "Blender",
            "time": time.time(),
        }

        return json.dumps(data)  # return the string version of the dict, as the payload requires a string
    
    response = requests.request(  # grabs the response of the POST request
        method="POST",
        url="https://wakatime.com/api/v1/users/current/heartbeats",
        headers=header(api_key),
        data=payload("Blender Projects", bpy.data.filepath, None)
    )
    
    return response  # returns the response so it can be displayed in console



TRIGGER_THREAD = False
ENABLE_THREAD = True
TRIGGER_EVENT = ''

def background_task():
    global ENABLE_THREAD, TRIGGER_THREAD
    while ENABLE_THREAD:
        time.sleep(1)
        if TRIGGER_THREAD:
            preferences = bpy.context.preferences
            op = preferences.addons[NAME].preferences
            
            response = post_to_wakatime(op.api_key)
            log(f"Status {response.status_code} | Text {response.text} | Event trigger '{TRIGGER_EVENT}'")
            TRIGGER_THREAD = False

GLOBAL_THREAD = threading.Thread(target=background_task)
def start_thread():
    global GLOBAL_THREAD
    try:
        GLOBAL_THREAD.start()
    except RuntimeError:
        log("Skipping request thread creation; already exists.")
    else:
        log("Thread for requests initialized.")

class WAKATIME_MT_preferences(AddonPreferences):
    """This stores the preference settings in the Add-On menu."""
    bl_idname = NAME

    api_key: StringProperty(
        name="Secret API Key",
        description="Paste your secret WakaTime API key",
        subtype='PASSWORD',
    )

    activate_button: BoolProperty(
        name="Activate Heartbeat",
        description="Click to transmit a heartbeat; useful for testing (see console)",
        default=False,
    )
    is_test_active: BoolProperty(
        name="Sleep Boolean",
        default=False,
    )

    enable_console: BoolProperty(
        name="Enable Console",
        description="Display console feedback",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_key")
        row = layout.row()
        console = row.row()
        console.enabled = self.enable_console
        console.label(text="(Load a new project or restart Blender to initialize.)")
        row.prop(self, "enable_console", text="Enable Console")

        console = layout.row()
        console.enabled = self.enable_console
        console.label(text="Curious? Click to transmit a heartbeat:", icon="EXPORT")
        
        if self.is_test_active:
            global TRIGGER_EVENT
            TRIGGER_EVENT = "Preferences"
            response = post_to_wakatime(self.api_key)
            log(f"Status {response.status_code} | Text {response.text} | Event trigger '{TRIGGER_EVENT}'")
            
            self.is_test_active = False
            self.activate_button = False
        
        if self.activate_button:
            console.prop(self, "activate_button", text="Sending...", toggle=True)
            self.is_test_active = True
        else:
            console.prop(self, "activate_button", text="Send", toggle=True)



class WAKATIME_OT_activate_listener(Operator):
    """Operator which runs its self from a timer"""
    bl_idname = "wakatime.listener"
    bl_label = "WakaTime Listener"

    _timer = None

    seconds_to_refresh_heartbeat: IntProperty(
        name="Seconds required before WakaTime is ready to accept keystrokes (officially 120)",
        default=120,
    )

    unix_of_last_heartbeat: IntProperty(
        name="Unix Timestamp of the Previous Heartbeat",
        default=0,
    )
    enable_heartbeats: BoolProperty(
        name="Enable Heartbeats",
        default=False,
    )


    def modal(self, context, event):
        global TRIGGER_THREAD, TRIGGER_EVENT

        current_time = int(time.time())
        if self.enable_heartbeats:
            if event.type not in {'TIMER', 'TIMER0', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'WINDOW_DEACTIVATE', 'TRACKPADPAN', 'OSKEY', 'NONE'}:
                #background_task()
                TRIGGER_THREAD = True
                TRIGGER_EVENT = event.type
                #log(f"{event.type} detected. Reseting clock.")
                self.unix_of_last_heartbeat = current_time
                self.enable_heartbeats = False
    
        elif event.type == 'TIMER':
            #print(f"{current_time:d}s - {self.unix_of_last_heartbeat:d}s")
            if self.unix_of_last_heartbeat == 0:
                self.unix_of_last_heartbeat = current_time
            elif current_time - self.unix_of_last_heartbeat > self.seconds_to_refresh_heartbeat:
                #log(f"Ready!")
                self.enable_heartbeats = True
        
        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

@ persistent # stay running across multiple files (used when the handler is part of an add-on).
def run_modal_operator(context):
    bpy.ops.wakatime.listener()
    log("Event listener initialized.")
    start_thread()



register_classes, unregister_classes = bpy.utils.register_classes_factory((
    WAKATIME_MT_preferences,
    WAKATIME_OT_activate_listener
))

def register():
    register_classes()
    bpy.app.handlers.load_post.append(run_modal_operator)
    

def unregister():
    global GLOBAL_THREAD, ENABLE_THREAD
    bpy.app.handlers.load_post.remove(run_modal_operator)
    
    ENABLE_THREAD = False
    log("Disabling thread...")
    try:
        GLOBAL_THREAD.join()
    except RuntimeError:
        log("Skipping request thread disabling; it never began.")
    else:
        log("Thread disabled!")

    unregister_classes()

if __name__ == "__main__":
    register()
