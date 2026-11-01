//go:build windows

package main

import (
	"log"
	"os"
	"path/filepath"
	"sessionlender/desktop/internal/config"
	"sessionlender/desktop/internal/desktop"
)

func main() {
	dir, err := config.DataDir()
	if err != nil {
		desktop.MessageBox("SessionLender", err.Error())
		return
	}
	logPath := filepath.Join(dir, "desktop.log")
	if info, statErr := os.Stat(logPath); statErr == nil && info.Size() > 1024*1024 {
		_ = os.Remove(logPath + ".old")
		_ = os.Rename(logPath, logPath+".old")
	}
	file, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err == nil {
		defer file.Close()
		log.SetOutput(file)
	}
	release, alreadyRunning, err := desktop.SingleInstance()
	if err != nil {
		desktop.MessageBox("SessionLender", err.Error())
		return
	}
	if alreadyRunning {
		return
	}
	defer release()
	if err := desktop.Run(); err != nil {
		log.Print(err)
		desktop.MessageBox("SessionLender", err.Error())
	}
}
