# IPC2ACTIVEMQ INSTALLATION

./install_python.sh
sudo python2.6 install_dependencies.py
if [ $? != 0 ]
then
  echo "[PYTHON DEPENDENCIES NOT INSTALLED. ABORTING.]"
else
  ./install_nebpublisher.sh
  if [ $? != 0 ]
  then
    echo "[DAEMON NOT INSTALLED. ABORTING.]"
  else
    echo "[IPC2ACTIVEMQ INSTALLED.]"
  fi
fi
