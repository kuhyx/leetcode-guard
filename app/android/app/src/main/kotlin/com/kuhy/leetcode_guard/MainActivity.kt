package com.kuhy.leetcode_guard

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // external_launch.dart: a kuhytutor:// link goes to com.kuhy.tutor
        // only; a phone slot's test build of the tutor claims the same scheme.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.kuhy.leetcode_guard/open")
            .setMethodCallHandler { call, result ->
                if (call.method != "view") return@setMethodCallHandler result.notImplemented()
                val url = call.argument<String>("url")
                val pkg = call.argument<String>("package")
                if (url == null || pkg == null) return@setMethodCallHandler result.success(false)
                val view = Intent(Intent.ACTION_VIEW, Uri.parse(url)).setPackage(pkg)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                try {
                    startActivity(view)
                    result.success(true)
                } catch (_: ActivityNotFoundException) {
                    result.success(false)
                }
            }
    }
}
