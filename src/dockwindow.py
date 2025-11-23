import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango
import sys
import os
import subprocess
import re
import math
import threading
import requests


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

apihost = "https://api.silverflag.net"

class RemoteDictionary:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.pending_word = None
    
    def lookup(self, word, callback):
        self.pending_word = word
        
        def fetch():
            try:
                r = requests.get(f"{self.base}/lookup/{word}", timeout=2)
                # Only callback if this is still the current word
                if word == self.pending_word:
                    result = r.json() if r.status_code == 200 else None
                    GLib.idle_add(callback, result)
            except Exception as e:
                if word == self.pending_word:
                    print(f"Dictionary error: {e}")
                    GLib.idle_add(callback, None)
        
        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()


class Settings:
    searchbar_width = 600
    searchbar_height = 60
    search_border_color = "#2d2d2d"
    entry_section_color = "#3d3d3d"
    result_text_color = "#ffffff"


class SpotlightSearch:
    def __init__(self):
        self.window = None
        self.entry = None
        self.results_box = None
        self.is_visible = False
        self.ai_textview = None
        self.ai_buffer = None
        self.ai_streaming = False
        self.ai_timeout_id = None
        
        try:
            self.dictionary = RemoteDictionary(apihost)
        except Exception as e:
            print(f"Dictionary not loaded: {e}")
            self.dictionary = None
        
        self.apps = self.load_desktop_apps()
    
    def load_desktop_apps(self):
        apps = []
        desktop_dirs = [
            '/usr/share/applications',
            '/usr/local/share/applications',
            os.path.expanduser('~/.local/share/applications')
        ]
        
        for desktop_dir in desktop_dirs:
            if not os.path.exists(desktop_dir):
                continue
            for filename in os.listdir(desktop_dir):
                if filename.endswith('.desktop'):
                    filepath = os.path.join(desktop_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            name = None
                            exec_cmd = None
                            for line in f:
                                if line.startswith('Name='):
                                    name = line.split('=', 1)[1].strip()
                                elif line.startswith('Exec='):
                                    exec_cmd = line.split('=', 1)[1].strip()
                                    exec_cmd = exec_cmd.split('%')[0].strip()
                            if name and exec_cmd:
                                apps.append({'name': name, 'exec': exec_cmd})
                    except:
                        pass
        
        return apps
    
    def create_window(self):
        self.window = Gtk.Window()
        self.window.set_title("SpotlightSearch")
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        
        # minimal css, reminder: old /home/dread/oldcss.txt
        css = f"""
            window {{ background-color: {Settings.search_border_color}; }}
            entry {{
                background-color: {Settings.entry_section_color};
                color: #ffffff;
                border: none;
                padding: 10px;
                font-size: 16px;
            }}
            label {{ color: #ffffff; padding: 5px; }}
            textview {{
                background-color: #3d3d3d;
                color: {Settings.result_text_color};
                padding: 10px;
                font-family: monospace;
            }}
            textview text {{ background-color: #3d3d3d; color: #ffffff; }}
            .section-header {{
                color: #888888;
                font-size: 11px;
                font-weight: bold;
                padding: 8px 5px 3px 5px;
            }}
            .result-pos {{
                color: #888888;
                font-style: italic;
                font-size: 12px;
                min-width: 80px;
            }}
            .result-def {{ color: #cccccc; font-size: 13px; }}
            .result-calc {{
                color: #5eaeff;
                font-size: 18px;
                font-weight: bold;
            }}
            .result-app {{ color: #ffffff; font-size: 14px; }}
            .result-separator {{
                background-color: #444444;
                min-height: 1px;
                margin: 5px 0;
            }}
        """
        
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        main_box.set_margin_top(15)
        main_box.set_margin_bottom(15)
        
        self.entry = Gtk.Entry()
        main_box.pack_start(self.entry, False, False, 0)
        
        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.results_box.set_margin_top(10)
        main_box.pack_start(self.results_box, False, False, 0)
        
        self.window.add(main_box)
        self.entry.connect('changed', self.on_key_release)
        self.entry.connect('activate', self.on_enter)
        self.window.connect('key-press-event', self.on_key_press)
        
        self.window.set_default_size(Settings.searchbar_width, Settings.searchbar_height)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_opacity(0.85)
        self.window.hide()
    
    def add_section_header(self, text):
        header = Gtk.Label()
        header.set_text(text.upper())
        header.set_xalign(0)
        header.get_style_context().add_class('section-header')
        self.results_box.pack_start(header, False, False, 0)
    
    def add_separator(self):
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.get_style_context().add_class('result-separator')
        self.results_box.pack_start(sep, False, False, 0)
    
    def safe_eval_math(self, expr):
        expr = expr.replace(' ', '').replace('^', '**')
        if not re.match(r'^[\d+\-*/%().]+$', expr):
            return None
        try:
            safe_dict = {
                "__builtins__": {},
                "abs": abs, "round": round, "pow": pow,
                "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
                "pi": math.pi, "e": math.e
            }
            return eval(expr, safe_dict, {})
        except:
            return None
    
    def apply_markdown_formatting(self, text_buffer, text):
        text_buffer.set_text("")
        text_buffer.create_tag("bold", weight=Pango.Weight.BOLD)
        text_buffer.create_tag("italic", style=Pango.Style.ITALIC)
        text_buffer.create_tag("code", family="monospace", background="#1a1a1a", foreground="#5eaeff")
        text_buffer.create_tag("heading", weight=Pango.Weight.BOLD, scale=1.2, foreground="#5eaeff")
        
        lines = text.split('\n')
        for line in lines:
            start_iter = text_buffer.get_end_iter()
            
            # handle heading formattings
            if line.startswith('### '):
                text_buffer.insert_with_tags_by_name(start_iter, line[4:] + '\n', "heading")
                continue
            elif line.startswith('## '):
                text_buffer.insert_with_tags_by_name(start_iter, line[3:] + '\n', "heading")
                continue
            elif line.startswith('# '):
                text_buffer.insert_with_tags_by_name(start_iter, line[2:] + '\n', "heading")
                continue
            
            # handle any inline formatting
            pos = 0
            while pos < len(line):
                if line[pos:pos+2] == '**':
                    end_pos = line.find('**', pos + 2)
                    if end_pos != -1:
                        start_iter = text_buffer.get_end_iter()
                        text_buffer.insert_with_tags_by_name(start_iter, line[pos+2:end_pos], "bold")
                        pos = end_pos + 2
                        continue
                
                if line[pos] == '*' and (pos + 1 >= len(line) or line[pos+1] != '*'):
                    end_pos = line.find('*', pos + 1)
                    if end_pos != -1 and (end_pos + 1 >= len(line) or line[end_pos+1] != '*'):
                        start_iter = text_buffer.get_end_iter()
                        text_buffer.insert_with_tags_by_name(start_iter, line[pos+1:end_pos], "italic")
                        pos = end_pos + 1
                        continue
                
                start_iter = text_buffer.get_end_iter()
                text_buffer.insert(start_iter, line[pos])
                pos += 1
            
            start_iter = text_buffer.get_end_iter()
            text_buffer.insert(start_iter, '\n')
    
    def fetch_ai_response(self, query):
        if self.ai_streaming:
            return
        
        self.ai_streaming = True
        
        def update_content():
            try:
                import urllib.parse
                encoded_query = urllib.parse.quote(query)
                r = requests.get(f"{apihost}/ai/question/{encoded_query}", timeout=30)
                
                if r.status_code == 200:
                    answer = r.json().get('answer', 'No response')
                    GLib.idle_add(lambda: self.apply_markdown_formatting(self.ai_buffer, answer) if self.ai_buffer else None)
                else:
                    GLib.idle_add(lambda: self.ai_buffer.set_text("Error: Could not get response") if self.ai_buffer else None)
                
                self.ai_streaming = False
            except Exception as e:
                print(f"AI error: {e}")
                GLib.idle_add(lambda: self.ai_buffer.set_text(f"Error: {str(e)}") if self.ai_buffer else None)
                self.ai_streaming = False
        
        thread = threading.Thread(target=update_content, daemon=True)
        thread.start()
    
    def update_results(self, query):
        # cancel pending
        if self.ai_timeout_id:
            GLib.source_remove(self.ai_timeout_id)
            self.ai_timeout_id = None
        
        # clear
        for child in self.results_box.get_children():
            self.results_box.remove(child)
        
        self.ai_textview = None
        self.ai_buffer = None
        
        if not query:
            self.resize_window(60)
            return
        
        total_height = 60
        has_results = False
        
        # diddy blud is doing
        has_math = any(c in query for c in ['+', '-', '*', '/', '(', ')', '^', '%'])
        if has_math or query.startswith('calc '):
            calc_query = query[5:] if query.startswith('calc ') else query
            result = self.safe_eval_math(calc_query)
            if result is not None:
                self.add_section_header("Calculator")
                result_label = Gtk.Label()
                result_label.set_text(str(result))
                result_label.set_xalign(0)
                result_label.get_style_context().add_class('result-calc')
                self.results_box.pack_start(result_label, False, False, 0)
                total_height += 50
                has_results = True
        
        # dictionary responses for single words
        words = query.strip().split()
        if len(words) == 1 and self.dictionary:
            if has_results:
                self.add_separator()
                total_height += 10
            
            self.add_section_header("Dictionary")
            total_height += 25
            loading_label = Gtk.Label()
            loading_label.set_text("Looking up...")
            loading_label.set_xalign(0)
            loading_label.get_style_context().add_class('result-def')
            self.results_box.pack_start(loading_label, False, False, 0)
            total_height += 30
            def on_dict_result(result):
                if loading_label.get_parent():
                    self.results_box.remove(loading_label)
                if result:
                    new_height = 60 + 25
                    for meaning in result.get('meanings', [])[:3]:
                        meaning_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
                        pos_label = Gtk.Label()
                        pos_label.set_text(meaning.get('part_of_speech', ''))
                        pos_label.set_xalign(0)
                        pos_label.get_style_context().add_class('result-pos')
                        meaning_box.pack_start(pos_label, False, False, 0)
                        
                        def_text = meaning.get('definition', '')[:120]
                        if len(meaning.get('definition', '')) > 120:
                            def_text += '...'
                        
                        def_label = Gtk.Label()
                        def_label.set_text(def_text)
                        def_label.set_xalign(0)
                        def_label.set_line_wrap(True)
                        def_label.set_max_width_chars(50)
                        def_label.get_style_context().add_class('result-def')
                        meaning_box.pack_start(def_label, True, True, 0)
                        
                        self.results_box.pack_start(meaning_box, False, False, 0)
                        new_height += 30
                    
                    self.results_box.show_all()
                    self.resize_window(min(new_height + 50, 500))
                else:
                    no_result = Gtk.Label()
                    no_result.set_text("No definition found")
                    no_result.set_xalign(0)
                    no_result.get_style_context().add_class('result-def')
                    self.results_box.pack_start(no_result, False, False, 0)
                    self.results_box.show_all()
                
                return False
            
            self.dictionary.lookup(words[0], on_dict_result)
            has_results = True
        
        # find apps
        matching_apps = [app for app in self.apps if query.lower() in app['name'].lower()][:3]
        if matching_apps:
            if has_results:
                self.add_separator()
                total_height += 10
            
            self.add_section_header("Applications")
            total_height += 25
            
            for app in matching_apps:
                app_label = Gtk.Label()
                app_label.set_text(app['name'])
                app_label.set_xalign(0)
                app_label.get_style_context().add_class('result-app')
                self.results_box.pack_start(app_label, False, False, 0)
                total_height += 28
            
            has_results = True
        
        # ai assistant for multi WORD!!! inputs
        if len(words) > 1 and not has_results:
            if has_results:
                self.add_separator()
                total_height += 10
            
            self.add_section_header("AI Assistant")
            total_height += 25
            
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_size_request(560, 200)
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            
            self.ai_textview = Gtk.TextView()
            self.ai_textview.set_editable(False)
            self.ai_textview.set_wrap_mode(Gtk.WrapMode.WORD)
            self.ai_textview.set_cursor_visible(False)
            self.ai_buffer = self.ai_textview.get_buffer()
            self.ai_buffer.set_text("Waiting...")
            
            scrolled.add(self.ai_textview)
            self.results_box.pack_start(scrolled, False, False, 0)
            
            total_height += 230
            has_results = True
            
            def trigger_ai():
                self.ai_buffer.set_text("Thinking...")
                self.fetch_ai_response(query)
                self.ai_timeout_id = None
                return False
            
            self.ai_timeout_id = GLib.timeout_add(1000, trigger_ai)
        
        if has_results:
            self.results_box.show_all()
            self.resize_window(min(total_height, 500))
        else:
            self.resize_window(60)
    
    def resize_window(self, height):
        self.window.resize(600, height)
    
    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide_window()
            return True
        return False
    
    def on_key_release(self, widget):
        query = self.entry.get_text()
        self.update_results(query)
    
    def on_enter(self, widget):
        query = self.entry.get_text()
        matching_apps = [app for app in self.apps if query.lower() in app['name'].lower()]
        if matching_apps:
            try:
                subprocess.Popen(matching_apps[0]['exec'], shell=True)
            except Exception as e:
                print(f"Failed to launch: {e}")
        self.hide_window()
    
    def show_window(self):
        if not self.is_visible:
            self.window.show_all()
            self.window.present()
            self.entry.set_text("")
            self.entry.grab_focus()
            for child in self.results_box.get_children():
                self.results_box.remove(child)
            self.resize_window(60)
            self.is_visible = True
    
    def hide_window(self):
        if self.is_visible:
            if self.ai_timeout_id:
                GLib.source_remove(self.ai_timeout_id)
                self.ai_timeout_id = None
            self.window.hide()
            self.is_visible = False
    
    def toggle_window(self):
        if self.is_visible:
            self.hide_window()
        else:
            self.show_window()
    
    def run(self):
        self.create_window()
        self.show_window()
        Gtk.main()


if __name__ == '__main__':
    search = SpotlightSearch()
    search.run()