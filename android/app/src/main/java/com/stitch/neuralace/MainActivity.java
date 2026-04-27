package com.stitch.neuralace;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
import com.stitch.neuralace.plugins.miband.MiBand6Plugin;
import com.stitch.neuralace.plugins.miband.PhoneSensorPlugin;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(MiBand6Plugin.class);
        registerPlugin(PhoneSensorPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
