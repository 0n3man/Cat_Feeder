<!DOCTYPE html>
<html>
<head>
<title>HTML Frames</title>
</head>
<frameset cols="85%,15%">
   <frame name="webcam" src="/webcam.php" />
   <frame name="control" src="/control-child.php" />
    <noframes>
   <body>
      Your browser does not support frames.
   </body>
   </noframes>
</frameset>
</html>
