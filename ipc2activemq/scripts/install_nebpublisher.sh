cd ../src
sudo python2.7 setup.py install
if [ $? != 0 ]
then
  echo "[NEBPUBLISHER NOT INSTALLED. ABORTING.]"
else
  echo "[NEBPUBLISHER SUCCESSFULLY INSTALLED.]"
fi

