pinctrl set 23 op dl   # EN ON
pinctrl set 17 op dh   # DIR

for i in $(seq 1 300)
do
  pinctrl set 27 op dh
  sleep 0.01
  pinctrl set 27 op dl
  sleep 0.01
done
