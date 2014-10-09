#!/usr/bin/python

import sys, subprocess, time, urllib2, socket, getopt, io
import threading, Queue, json
import re, datetime, os, platform

MinerProcess = None

class Statistic:
	# Initialize Instance
	def __init__(self):
		self.Name = ""
		self.Started = datetime.datetime.now()
		self.LastUpdate = time.time()
		self.UpdateEvery = 86400
		self.Counter = 0
		self.RunningCounter = 0
		self.RunningAverage = 0

	# Step Counter
	def Step(self,count):
		c = time.time() - self.LastUpdate

		if (c >= self.UpdateEvery):
			self.Update()

		self.Counter = self.Counter + count
		self.RunningCount = self.RunningCounter + count

	# Update Period (without checking if period has expired, you should not call this, Step() will
	def Update(self):
		self.LastUpdate = time.time()
		self.RunningAverage = (self.RunningAverage + self.Counter) / 2
		self.Counter = 0

	# Print out statistic
	def Print(self,fileObj=None):
		if fileObj == None:
			fileObj = sys.stdout

		units = self.SmallestUnit()
		fileObj.write('{0}/{1} - {2} since {3}'.format(self.RunningAverage,units[0],self.Counter,self.LastUpdate))

	def SmallestUnit(self):
		list = [ [ "Year", 220752000.0 ], [ "Week", 604800.0 ], [ "Day", 86400.0 ], [ "Hour", 3600.0 ], [ "Minute", 60.0 ], [ "Second", 1.0 ], [ "Tenth/sec", 0.1 ], [ "Hundreth/sec", 0.01 ], [ "Millisecond", 0.001 ], [ "Microsecond", 0.0000001 ] ]

		lastPeriod = [ list[0][0], list[0][1] ]
		period = None
		periodName = None

		for periodName, period in list:
			r = self.UpdateEvery/period

			lastPeriod = [ periodName, period ] 

			if r >= 1 and r <= 100:
				break

		return lastPeriod

def FileExists(fileName):
	flag=False

	try:
		p = open(fileName, 'r')
		p.close()
		flag = True
	except:
		flag = False

	return (flag)

# Is Architecture 64 Bits
def Is64():
	return sys.maxsize > 2**32

# Is Architecture Unix (or at least, non windows)
def Unix():
	return (not sys.platform.startswith('win32'))

# Determine NightTime
def IsNightTime():
	if (datetime.datetime.now().hour > 21 or datetime.datetime.now().hour < 7):
		return True

	return False

# Send Cube Commands
def SendCube(cmds):
	cmdList = ["/opt/scripts/sendCube.py"]

	if (Unix() and FileExists(cmdList[0])):
		for i in cmds:
			cmdList.append(i)

		subprocess.call(cmdList) 

# Signal and Accepted Hash
def SignalAccept(nightMode):
	SendCube(["pattern","9"])

	time.sleep(10)

	if not nightMode:
		SendCube(["demo"])
	else:
		SendCube(["off"])

	return

def Log(line, statObj = None, logName="/tmp/miner.log"):
	fp = open(logName,"a")
	fp.write(line)

	if (statObj != None):
		fp.write(" : ")
		statObj.Print(fp)

	fp.write("\n")
	fp.close()

# Usage
def Usage():
	print "minerShell.py [-l] [-p|--pool <poolname>] [-t|--threads <threadcount>] [-i]"
	print "-l\tEnable logging to /tmp/miner.log"
	print "-i\tImmediate execution"
	print "-p\tPool Name"
	print "-t\tThreads"
	print "-x\tTest, execute all commands, but do not run miner"
	return

# Convert
def Convert(data):
	return repr(data).strip("'").replace(" ","")

# Start Server
def StartServer():
	Host = ""
	Port = 5001
	
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.bind((Host, Port))
	s.listen(1)
	s.setblocking(0);

	return s

# Process Net Commands
def ProcessCmds(listeningSocket):
	global MinerProcess

	try:
		conn, addr = listeningSocket.accept()

		data = conn.recv(1024)

		if not data:
			return

		strData = Convert(data)

		cmds = strData.split()

		if cmds[0] == "hostinfo":
			Log("Recieved HostInfo Request")
			conn.sendall('ok {0}'.format("|".join(platform.uname())))
		elif cmds[0] == "ping":
			Log("Recieved Ping")
			conn.sendall("ok pong")
		elif cmds[0] == "quit":
			Log("Recieved Quit Request")
			conn.sendall("ok quitting")
			Log('Killing miner process {0}'.format(MinerProcess.pid))
			MinerProcess.kill()
		else:
			Log("Recieved Bad Remote Command")
			conn.sendall("err bad command")

		conn.shutdown(socket.SHUT_RDWR)
		conn.close()
	except socket.error:
		pass
	except Exception as msg:
		Log(str(msg))

	return

# Miner Shell Procedure
def minerShell(args):
	global MinerProcess
	nightMode = IsNightTime()
	testMode = False
	logging = False
	terminate = False
	cubeAvailable = True
	userName = "ejohnfel"
	password = "qw3rty"
	pool = "Common"
	userpass=""
	pause=True

	minerOpts = ["/usr/local/bin/minerd","-a","scrypt","--retry-pause=120","--url=stratum+tcp://ltc.mupool.com"]

	try:
		opts, argList = getopt.getopt(args,"hp:t:ilx",["pool","threads"])
	except getopt.GetoptError:
		if len(args) > 0:
			Usage()
			sys.exit(2)
		else:
			return

	for opt,arg in opts:
		if opt in ("-h"):
			Usage()
			sys.exit(0)
		elif opt in ("-p","--pool"):
			userpass = '--userpass=={0}.{1}:{2}'.format(userName,arg,password)
			minerOpts.append(userpass)
		elif opt in ("-t","--threads"):
			minerOpts.append('--threads={0}'.format(arg))
		elif opt in ("-i"):
			pause = False
		elif opt in ("-l"):
			logging = True
		elif opt in ("-x"):
			testMode = True

	if (userpass == ""):
		userpass='--userpass={0}.{1}:{2}'.format(userName,pool,password)
		minerOpts.append(userpass)

	if pause:
		print("Sleeping for Delay")
		time.sleep(1*60)

	if (not testMode):
		MinerProcess = subprocess.Popen(minerOpts,stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

		newBlockStat = Statistic()
		acceptedStat = Statistic()
		kHashStat = Statistic()

		kHashStat.UpdateEvery = 3600
		acceptedStat.UpdateEvery = 3600
		newBlockStat.UpdateEvery = 3600

		if logging:
			Log('Logging Began : {0}'.format(datetime.datetime.now()))

		listeningSocket = StartServer()

		while terminate != True:
			if IsNightTime():
				if not nightMode:
					SendCube(["off"])

				nightMode = True
			else:
				nightMode = False

			line = MinerProcess.stdout.readline()

			if line == None or line == "":
				line = MinerProcess.stderr.readline()

			line = line.strip("\n")

			if re.search("Stratum",line) != None:
				newBlockStat.Step(1)
				if logging:
					Log(line,newBlockStat)
					Log("Hash Stats :", kHashStat)
			elif re.search("accepted",line) != None:
				acceptedStat.Step(1)
				if cubeAvailable:
					SignalAccept(nightMode)
				if logging:
					Log(line,acceptedStat)
			elif re.search("khash",line) != None:
				lineParts = re.split("[\s]+",line)
				value = int(lineParts[4])
				kHashStat.Step(value)
				if logging:
					Log(line,logName="/tmp/hash.log")

			MinerProcess.poll()
			ProcessCmds(listeningSocket)

			if MinerProcess.returncode != None:
				terminate = True

	listeningSocket.shutdown(socket.SHUT_RDWR)
	listeningSocket.close()

	return

# Main Loop

if __name__ == "__main__":
	print("Miner Shell v0.5")

	minerShell(sys.argv[1:])
