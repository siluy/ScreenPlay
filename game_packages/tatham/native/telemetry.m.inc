/* Runs inside the original Cocoa frontend. Only exports state to the trusted runner. */
- (void)gameworldTelemetry:(id)sender
{
    const char *dest = getenv("GAMEWORLD_STATE_FILE");
    if (!dest) return;
    NSMutableData *save = [NSMutableData data];
    midend_serialise(me, gw_write_data, save);
    NSRect viewRect = [self convertRectToScreen:[fe.view convertRect:[fe.view bounds] toView:nil]];
    CGFloat screenTop = [[[NSScreen screens] objectAtIndex:0] frame].size.height;
    NSString *serialized = [[[NSString alloc] initWithData:save encoding:NSUTF8StringEncoding] autorelease];
    NSDictionary *record = @{
        @"schema_version": @"0.1", @"pid": @([[NSProcessInfo processInfo] processIdentifier]),
        @"session": [NSString stringWithUTF8String:getenv("GAMEWORLD_SESSION") ?: ""],
        @"game": [NSString stringWithUTF8String:ourgame->name],
        @"status": @(midend_status(me)), @"serialized": serialized ?: @"",
        @"captured_at": @([[NSDate date] timeIntervalSince1970]),
        @"viewport": @{@"x": @(viewRect.origin.x), @"y": @(screenTop - NSMaxY(viewRect)),
            @"width": @(fe.w), @"height": @(fe.h)},
        @"window_number": @([self windowNumber])
    };
    NSData *json = [NSJSONSerialization dataWithJSONObject:record options:0 error:nil];
    [json writeToFile:[NSString stringWithUTF8String:dest] atomically:YES];
    /* Optional development artifact: the original game's own rendered pixels.
       This is not a desktop screenshot and is never substituted by the runner. */
    const char *renderDest = getenv("GAMEWORLD_RENDER_FILE");
    if (renderDest) {
        NSBitmapImageRep *bitmap = [NSBitmapImageRep imageRepWithData:[fe.image TIFFRepresentation]];
        NSData *png = [bitmap representationUsingType:NSPNGFileType properties:@{}];
        [png writeToFile:[NSString stringWithUTF8String:renderDest] atomically:YES];
    }
}
